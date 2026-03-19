import json
import os
import shutil

from config import load_config
from .utils import run_external


HIGH_VALUE_FRAMEWORKS = {
    "redis",
    "mongodb",
    "elasticsearch",
    "mysql",
    "postgresql",
    "spring",
    "jenkins",
    "gitlab",
    "nacos",
    "swagger",
    "minio",
    "harbor",
    "rabbitmq",
    "weblogic",
    "jboss",
    "tomcat",
    "shiro",
}
HIGH_VALUE_PORTS = {6379, 27017, 9200, 3306, 5432, 2375, 8848}
HIGH_VALUE_TITLES = ["登录", "admin", "管理", "后台", "系统"]


def _ensure_output_dir(cfg):
    out_dir = cfg.get("agent", {}).get("output_dir", "./output")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _next_raw_path(out_dir, prefix):
    idx = 1
    while True:
        path = os.path.join(out_dir, f"raw_{prefix}_{idx}.txt")
        if not os.path.exists(path):
            return path
        idx += 1


def _resolve_tool_path(tool_path, tool_name):
    if not tool_path:
        return None, f"Error: {tool_name} path is empty in config.yaml"

    if os.path.sep in tool_path or "/" in tool_path:
        abs_path = os.path.abspath(tool_path)
        if not os.path.exists(abs_path):
            hint = os.path.basename(tool_path) or tool_name
            return (
                None,
                f"Error: {tool_name} tool not found: {tool_path}\n"
                f"请检查路径并执行 {hint} --help 查看用法",
            )
        return abs_path, None

    found = shutil.which(tool_path)
    if not found:
        return (
            None,
            f"Error: {tool_name} tool not found in PATH: {tool_path}\n"
            f"请检查安装并执行 {tool_name} --help 查看用法",
        )
    return found, None


def _load_state_if_exists(out_dir):
    state_path = os.path.join(out_dir, "state.json")
    if not os.path.isfile(state_path):
        return None, state_path

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)
    if not isinstance(state, dict):
        state = {}

    results = state.get("results")
    if not isinstance(results, dict):
        results = {}
        state["results"] = results

    return state, state_path


def _save_state(state, state_path):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _normalize_int(value, default=0):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _stringify_framework(raw):
    if isinstance(raw, list):
        return "/".join([str(x).strip() for x in raw if str(x).strip()])
    if isinstance(raw, dict):
        values = [str(v).strip() for v in raw.values() if str(v).strip()]
        return "/".join(values)
    return str(raw or "").strip()


def _parse_jsonl(raw_text):
    services = []
    for line in str(raw_text or "").splitlines():
        row = line.strip()
        if not row or not row.startswith("{"):
            continue

        try:
            obj = json.loads(row)
        except Exception:
            continue

        ip = str(
            obj.get("ip")
            or obj.get("host")
            or obj.get("addr")
            or obj.get("target")
            or ""
        ).strip()
        if not ip:
            continue

        port = _normalize_int(
            obj.get("port")
            or obj.get("port_id")
            or obj.get("portid")
            or obj.get("service_port"),
            default=-1,
        )
        if port <= 0:
            continue

        protocol = str(obj.get("protocol") or obj.get("proto") or "").strip().lower()
        framework = _stringify_framework(
            obj.get("frameworks")
            or obj.get("framework")
            or obj.get("service")
            or obj.get("product")
            or ""
        )
        title = str(
            obj.get("title")
            or obj.get("http_title")
            or obj.get("web_title")
            or ""
        ).strip()

        services.append(
            {
                "ip": ip,
                "port": port,
                "protocol": protocol,
                "framework": framework,
                "title": title,
            }
        )

    return services


def _is_high_value(item):
    framework = str(item.get("framework", "") or "").lower()
    title = str(item.get("title", "") or "").lower()
    port = _normalize_int(item.get("port"), default=0)

    if any(keyword in framework for keyword in HIGH_VALUE_FRAMEWORKS):
        return True
    if port in HIGH_VALUE_PORTS:
        return True
    if any(keyword in title for keyword in HIGH_VALUE_TITLES):
        return True
    return False


def _update_port_scan_state(state, target, services):
    results = state.get("results")
    if not isinstance(results, dict):
        results = {}
        state["results"] = results

    port_scan = results.get("port_scan")
    if not isinstance(port_scan, dict):
        port_scan = {"scanned_targets": [], "open_ports": {}}
        results["port_scan"] = port_scan

    scanned_targets = port_scan.get("scanned_targets")
    if not isinstance(scanned_targets, list):
        scanned_targets = []
        port_scan["scanned_targets"] = scanned_targets

    if target not in scanned_targets:
        scanned_targets.append(target)

    open_ports = port_scan.get("open_ports")
    if not isinstance(open_ports, dict):
        open_ports = {}
        port_scan["open_ports"] = open_ports

    for item in services:
        ip = item.get("ip")
        port = _normalize_int(item.get("port"), default=-1)
        if not ip or port <= 0:
            continue

        ip_entries = open_ports.get(ip)
        if not isinstance(ip_entries, list):
            ip_entries = []
            open_ports[ip] = ip_entries

        existing_ports = {
            _normalize_int(x.get("port"), default=-1)
            for x in ip_entries
            if isinstance(x, dict)
        }
        if port in existing_ports:
            continue

        ip_entries.append(
            {
                "port": port,
                "protocol": str(item.get("protocol") or ""),
                "framework": str(item.get("framework") or ""),
                "title": str(item.get("title") or ""),
            }
        )


def gogo_scan(target, ports="top2", threads=0):
    try:
        target = str(target or "").strip()
        if not target:
            return "Error: target is required"

        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)

        gogo_path = cfg.get("tools", {}).get("gogo_path", "")
        gogo_bin, err = _resolve_tool_path(gogo_path, "gogo")
        if err:
            return err

        active_cfg = cfg.get("active", {})
        if not isinstance(active_cfg, dict):
            active_cfg = {}

        proxy = str(os.getenv("RECONMIND_ACTIVE_PROXY") or active_cfg.get("proxy") or "").strip()
        cfg_threads = _normalize_int(active_cfg.get("gogo_threads", 0), default=0)
        final_threads = _normalize_int(threads, default=0)

        if final_threads <= 0:
            if cfg_threads > 0:
                final_threads = cfg_threads
            else:
                final_threads = 20 if proxy else 1000

        cmd = [
            gogo_bin,
            "-i",
            target,
            "-p",
            str(ports or "top2"),
            "-t",
            str(final_threads),
            "-o",
            "jl",
            "-q",
        ]
        if proxy:
            cmd.extend(["--proxy", proxy])

        result, error = run_external(cmd, timeout=300)
        if error:
            return error

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        raw_text = f"{stdout}\n{stderr}".strip() if stderr else stdout

        raw_path = _next_raw_path(out_dir, "gogo")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        services = _parse_jsonl(raw_text)

        state, state_path = _load_state_if_exists(out_dir)
        state_note = f"已更新 state.json，原始结果: {raw_path}"
        if state is not None:
            _update_port_scan_state(state, target, services)
            _save_state(state, state_path)
        else:
            state_note = f"未检测到 state.json，原始结果: {raw_path}"

        high_value = [item for item in services if _is_high_value(item)]
        other_count = max(0, len(services) - len(high_value))

        lines = [f"扫描 {target}，发现 {len(services)} 个开放端口/服务"]
        lines.append("高价值服务")
        if high_value:
            for idx, item in enumerate(high_value[:15], 1):
                framework = item.get("framework") or "-"
                protocol = item.get("protocol") or "-"
                title = item.get("title") or "-"
                lines.append(
                    f"{idx}. {item['ip']}:{item['port']} | {protocol} | {framework} | {title}"
                )
            if len(high_value) > 15:
                lines.append(f"... 其余 {len(high_value) - 15} 条高价值服务未展开")
        else:
            lines.append("无")

        lines.append(f"其他服务: {other_count}")
        lines.append(state_note)
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gogo_scan",
            "description": "主动端口扫描+服务指纹识别，支持代理并自动更新 state.json 的 port_scan 字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "扫描目标，支持 IP 或 CIDR",
                    },
                    "ports": {
                        "type": "string",
                        "description": "端口范围，如 top2 / - / 1-65535",
                        "default": "top2",
                    },
                    "threads": {
                        "type": "integer",
                        "description": "并发线程数，0 为自动",
                        "default": 0,
                    },
                },
                "required": ["target"],
            },
        },
    }
]

FUNCTIONS = {"gogo_scan": gogo_scan}
