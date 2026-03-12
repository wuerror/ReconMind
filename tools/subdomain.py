import json
import os
import re
import shutil

from config import load_config
from .utils import run_external


HIGH_VALUE_PREFIXES = {
    "vpn",
    "oa",
    "mail",
    "sso",
    "admin",
    "manage",
    "api",
    "gateway",
    "jenkins",
    "gitlab",
    "jira",
    "zabbix",
    "grafana",
}


def _ensure_output_dir(cfg):
    out_dir = cfg.get("agent", {}).get("output_dir", "./output")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _timeout(cfg):
    try:
        return int(cfg.get("agent", {}).get("timeout", 120))
    except Exception:
        return 120


def _next_raw_path(out_dir, prefix):
    idx = 1
    while True:
        path = os.path.join(out_dir, f"raw_{prefix}_{idx}.txt")
        if not os.path.exists(path):
            return path
        idx += 1


def _load_state(out_dir):
    state_path = os.path.join(out_dir, "state.json")
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = {}

    if not isinstance(state, dict):
        state = {}

    results = state.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        state["results"] = results

    for key in ["domains", "subdomains", "ips", "urls", "emails"]:
        if not isinstance(results.get(key), list):
            results[key] = []

    return state, state_path


def _save_state(state, state_path):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _append_unique(dst, items):
    seen = set(dst)
    added = []
    for item in items:
        if item and item not in seen:
            dst.append(item)
            seen.add(item)
            added.append(item)
    return added


def _resolve_tool_path(tool_path, tool_name):
    if not tool_path:
        return None, f"Error: {tool_name} path is empty in config.yaml"

    if os.path.sep in tool_path or "/" in tool_path:
        abs_path = os.path.abspath(tool_path)
        if not os.path.exists(abs_path):
            return None, f"Error: {tool_name} tool not found: {tool_path}"
        return abs_path, None

    found = shutil.which(tool_path)
    if not found:
        return None, f"Error: {tool_name} tool not found in PATH: {tool_path}"
    return found, None


def _extract_subdomains(text, domain):
    root = str(domain).strip().lower().lstrip("*.")
    if not root:
        return []

    pattern = re.compile(rf"\b(?:[A-Za-z0-9_-]+\.)+{re.escape(root)}\b", re.IGNORECASE)
    found = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        for match in pattern.findall(line):
            item = match.lower().strip(".")
            if item and item.endswith("." + root):
                found.add(item)

        candidate = line.lower().strip(".")
        if candidate.endswith("." + root):
            found.add(candidate)

    return sorted(found)


def _high_value_subdomains(items):
    high = []
    for sub in items:
        prefix = sub.split(".", 1)[0].lower()
        if prefix in HIGH_VALUE_PREFIXES:
            high.append(sub)
    return sorted(set(high))


def _sync_subdomain_txt(out_dir, all_subdomains):
    txt_path = os.path.join(out_dir, "subdomain.txt")
    unique_sorted = sorted(set(all_subdomains))
    with open(txt_path, "w", encoding="utf-8") as f:
        if unique_sorted:
            f.write("\n".join(unique_sorted) + "\n")
        else:
            f.write("")
    return txt_path


def subfinder(domain):
    try:
        if not domain or not str(domain).strip():
            return "Error: domain is required"

        domain = str(domain).strip().lower().lstrip("*.")
        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)
        timeout = _timeout(cfg)

        tool_path = cfg.get("tools", {}).get("subfinder_path", "subfinder")
        cmd_bin, err = _resolve_tool_path(tool_path, "subfinder")
        if err:
            return err

        result, error = run_external([cmd_bin, "-d", domain, "-silent"], timeout=timeout)
        if error:
            return error

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        raw_text = f"{stdout}\n{stderr}".strip() if stderr else stdout

        raw_path = _next_raw_path(out_dir, "subfinder")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        found = _extract_subdomains(raw_text, domain)
        state, state_path = _load_state(out_dir)
        all_subdomains = state["results"]["subdomains"]
        added = _append_unique(all_subdomains, found)
        _save_state(state, state_path)

        txt_path = _sync_subdomain_txt(out_dir, all_subdomains)
        high_value = _high_value_subdomains(found)
        high_text = ", ".join(high_value) if high_value else "无"

        return (
            f"{domain}: 发现 {len(found)} 个子域名（新增 {len(added)} 个）\n"
            f"高价值: {high_text}\n"
            f"已更新 state.json 和 subdomain.txt（{txt_path}），原始输出: {raw_path}"
        )
    except Exception as e:
        return f"Error: {e}"


def ksubdomain(domain, wordlist="default"):
    try:
        if not domain or not str(domain).strip():
            return "Error: domain is required"

        domain = str(domain).strip().lower().lstrip("*.")
        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)
        timeout = max(_timeout(cfg), 180)

        tool_path = cfg.get("tools", {}).get("ksubdomain_path", "ksubdomain")
        cmd_bin, err = _resolve_tool_path(tool_path, "ksubdomain")
        if err:
            return err

        cmd = [cmd_bin, "enum", "-d", domain]
        if wordlist and str(wordlist).strip().lower() != "default":
            cmd.extend(["-f", str(wordlist).strip()])

        result, error = run_external(cmd, timeout=timeout)
        if error:
            return error

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        raw_text = f"{stdout}\n{stderr}".strip() if stderr else stdout

        raw_path = _next_raw_path(out_dir, "ksubdomain")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        found = _extract_subdomains(raw_text, domain)
        state, state_path = _load_state(out_dir)
        all_subdomains = state["results"]["subdomains"]
        added = _append_unique(all_subdomains, found)
        _save_state(state, state_path)

        txt_path = _sync_subdomain_txt(out_dir, all_subdomains)
        high_value = _high_value_subdomains(found)
        high_text = ", ".join(high_value) if high_value else "无"

        return (
            f"{domain}: 发现 {len(found)} 个子域名（新增 {len(added)} 个）\n"
            f"高价值: {high_text}\n"
            f"已更新 state.json 和 subdomain.txt（{txt_path}），原始输出: {raw_path}"
        )
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "subfinder",
            "description": "被动收集子域名。自动去重并更新state.json(subdomains字段)和subdomain.txt。返回发现摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "目标域名"},
                },
                "required": ["domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ksubdomain",
            "description": "DNS爆破验证子域名。自动去重并更新state.json和subdomain.txt。返回发现摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "目标域名"},
                    "wordlist": {
                        "type": "string",
                        "description": "字典文件路径",
                        "default": "default",
                    },
                },
                "required": ["domain"],
            },
        },
    },
]

FUNCTIONS = {
    "subfinder": subfinder,
    "ksubdomain": ksubdomain,
}
