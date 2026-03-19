import json
import os
import re
import shutil
from collections import Counter
from html import unescape
from urllib.parse import urljoin, urlparse

from config import load_config
from .utils import run_external


HIGH_VALUE_COMPONENTS = {
    "spring boot": "Spring Boot",
    "actuator": "Actuator",
    "swagger": "Swagger",
    "druid": "Druid",
    "shiro": "Shiro",
    "thinkphp": "ThinkPHP",
    "struts": "Struts",
    "weblogic": "WebLogic",
    "jboss": "JBoss",
    "jenkins": "Jenkins",
    "gitlab": "GitLab",
    "jira": "Jira",
    "zabbix": "Zabbix",
    "grafana": "Grafana",
    "nacos": "Nacos",
    "apollo": "Apollo",
    "minio": "MinIO",
    "harbor": "Harbor",
    "rabbitmq": "RabbitMQ",
    "elasticsearch": "Elasticsearch",
}

HIGH_VALUE_TITLE_MARKERS = [
    ("登录", "登录入口"),
    ("admin", "登录入口"),
    ("管理", "管理后台"),
    ("后台", "管理后台"),
    ("oa", "OA入口"),
    ("erp", "ERP入口"),
    ("crm", "CRM入口"),
]

LOW_VALUE_TITLE_MARKERS = ["cdn", "默认", "建设中", "停放", "coming soon"]

POWERED_BY_RE = re.compile(r"powered by[^<]{0,80}", re.IGNORECASE)
COPYRIGHT_RE = re.compile(r"copyright[^<]{0,80}", re.IGNORECASE)


def _ensure_output_dir(cfg):
    out_dir = cfg.get("agent", {}).get("output_dir", "./output")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _load_state(out_dir):
    state_path = os.path.join(out_dir, "state.json")
    if os.path.exists(state_path):
        with open(state_path, "r", encoding="utf-8") as f:
            try:
                state = json.load(f)
            except Exception:
                state = {}
    else:
        state = {}

    if not isinstance(state, dict):
        state = {}

    results = state.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        state["results"] = results

    fingerprints = results.setdefault("fingerprints", {})
    if not isinstance(fingerprints, dict):
        fingerprints = {}
        results["fingerprints"] = fingerprints

    return state, state_path


def _save_state(state, state_path):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _next_raw_path(out_dir, prefix):
    idx = 1
    while True:
        path = os.path.join(out_dir, f"raw_{prefix}_{idx}.txt")
        if not os.path.exists(path):
            return path
        idx += 1


def _resolve_tool_path(cfg):
    tool_path = cfg.get("tools", {}).get("observer_ward_path", "observer_ward")
    if not tool_path:
        return None, "Error: 未在 config.yaml 中配置 tools.observer_ward_path"

    if os.path.sep in tool_path or "/" in tool_path:
        abs_path = os.path.abspath(tool_path)
        if not os.path.exists(abs_path):
            return None, f"Error: 未找到 observer_ward 可执行文件: {tool_path}"
        return abs_path, None

    found = shutil.which(tool_path)
    if not found:
        return None, f"Error: 未在 PATH 中找到 observer_ward 可执行文件 ({tool_path})"
    return found, None


def _extract_entries(raw_text):
    if not raw_text:
        return []

    candidates = [raw_text.strip()]
    if raw_text.strip().startswith("{"):
        brace_pos = raw_text.find("[")
        if brace_pos > 0:
            candidates.append(raw_text[brace_pos:].strip())
    elif raw_text.strip().startswith("["):
        candidates.append(raw_text.strip())

    entries = []
    for text in candidates:
        if not text:
            continue
        try:
            data = json.loads(text)
        except Exception:
            continue

        if isinstance(data, list):
            entries.extend([item for item in data if isinstance(item, dict)])
            if entries:
                return entries
        elif isinstance(data, dict):
            for key in ("data", "results", "items", "list"):
                value = data.get(key)
                if isinstance(value, list):
                    subset = [item for item in value if isinstance(item, dict)]
                    if subset:
                        return subset
            entries.append(data)
            return entries

    # 尝试逐行解析
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            entries.append(obj)
        elif isinstance(obj, list):
            entries.extend([item for item in obj if isinstance(item, dict)])
    return entries


def _extract_url(entry):
    for key in ("url", "link", "site", "target", "host"):
        value = entry.get(key)
        if value:
            return str(value).strip()
    return ""


def _extract_title(entry):
    title = entry.get("title") or entry.get("web_title") or entry.get("http_title") or ""
    return str(title).strip()


def _extract_fingerprints(entry):
    fps = entry.get("fingerprint")
    if fps is None:
        fps = entry.get("fingerprints")
    if fps is None:
        fps = entry.get("apps")

    names = []
    if isinstance(fps, list):
        for item in fps:
            if isinstance(item, dict):
                name = item.get("cms") or item.get("name") or item.get("product") or ""
                version = item.get("version") or item.get("ver") or ""
                text = str(name).strip()
                if text:
                    if version and str(version).strip():
                        text = f"{text} {str(version).strip()}"
                    names.append(text)
            elif isinstance(item, str):
                value = item.strip()
                if value:
                    names.append(value)
    elif isinstance(fps, dict):
        name = fps.get("cms") or fps.get("name") or fps.get("product") or ""
        version = fps.get("version") or fps.get("ver") or ""
        text = str(name).strip()
        if text:
            if version and str(version).strip():
                text = f"{text} {str(version).strip()}"
            names.append(text)
    elif isinstance(fps, str):
        value = fps.strip()
        if value:
            names.append(value)

    deduped = []
    seen = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped


def _match_high_component(fp_names):
    for name in fp_names:
        lower = name.lower()
        for key, label in HIGH_VALUE_COMPONENTS.items():
            if key in lower:
                return label
    return ""


def _match_high_title(title):
    lower = title.lower()
    for marker, label in HIGH_VALUE_TITLE_MARKERS:
        if marker.lower() in lower:
            return label
    return ""


def _low_value_label(title):
    if not title:
        return "(空title)"
    lower = title.lower()
    for marker in LOW_VALUE_TITLE_MARKERS:
        if marker in lower:
            return f"title含{marker}"
    return title


def _summarize_counter(counter):
    if not counter:
        return "无"
    parts = [f"{label}×{count}" for label, count in counter.most_common()]
    return ", ".join(parts)


def _analyze_entries(entries):
    stats = {
        "total": 0,
        "recognized": 0,
        "high": Counter(),
        "mid": Counter(),
        "low": Counter(),
        "unrecognized": [],
        "records": [],
    }
    seen_unrecognized = set()

    for entry in entries:
        url = _extract_url(entry)
        if not url:
            continue
        title = _extract_title(entry)
        fp_names = _extract_fingerprints(entry)
        stats["total"] += 1

        high_label = _match_high_component(fp_names) or _match_high_title(title)
        if fp_names:
            stats["recognized"] += 1
            desc = "; ".join(fp_names)
            stats["records"].append((url, desc))
            if high_label:
                stats["high"][high_label] += 1
            else:
                stats["mid"][fp_names[0]] += 1
        else:
            if high_label:
                stats["high"][high_label] += 1
            else:
                stats["low"][_low_value_label(title)] += 1
            if url not in seen_unrecognized:
                stats["unrecognized"].append(url)
                seen_unrecognized.add(url)

    return stats


def _update_fingerprint_state(out_dir, records):
    if not records:
        return False

    state, state_path = _load_state(out_dir)
    fingerprints = state["results"]["fingerprints"]
    updated = False
    for url, desc in records:
        if not url or not desc:
            continue
        existing = fingerprints.get(url)
        if isinstance(existing, dict):
            continue
        if existing == desc:
            continue
        fingerprints[url] = desc
        updated = True

    if updated:
        _save_state(state, state_path)
    return updated


def _format_observer_summary(stats, raw_path, updated):
    total = stats["total"]
    recognized = stats["recognized"]
    high_text = _summarize_counter(stats["high"])
    mid_text = _summarize_counter(stats["mid"])
    low_count = sum(stats["low"].values())
    low_text = _summarize_counter(stats["low"])

    lines = [
        f"observer_ward 识别 {recognized}/{total} 个URL",
        f"原始结果: {raw_path}",
        f"高价值({sum(stats['high'].values())}): {high_text}",
        f"中价值({sum(stats['mid'].values())}): {mid_text}",
        f"低价值/未识别({low_count}): {low_text}",
    ]

    if stats["unrecognized"]:
        lines.append(f"未识别URL({len(stats['unrecognized'])}):")
        for url in stats["unrecognized"]:
            lines.append(f"- {url}")
    else:
        lines.append("未识别URL(0): 无")

    if updated:
        lines.append("state.json 已更新 fingerprints 字段")
    else:
        lines.append("state.json 无需更新（未发现新的指纹匹配）")

    return "\n".join(lines)


def observer_ward(targets):
    try:
        target_path = str(targets or "").strip()
        if not target_path:
            return "Error: targets is required"
        if not os.path.isfile(target_path):
            return f"Error: targets 文件不存在: {target_path}"

        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)
        timeout = max(int(cfg.get("agent", {}).get("timeout", 120)), 180)
        tool_bin, err = _resolve_tool_path(cfg)
        if err:
            return err

        cmd = [
            tool_bin,
            "-l",
            os.path.abspath(target_path),
            "--format",
            "json",
            "--silent",
        ]
        result, error = run_external(cmd, timeout=timeout)
        if error:
            return error

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        raw_text = stdout if stdout else stderr
        if stdout and stderr:
            raw_text = f"{stdout}\n{stderr}"

        raw_path = _next_raw_path(out_dir, "observer_ward")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        entries = _extract_entries(stdout) or _extract_entries(raw_text)
        if not entries:
            return f"Error: 未能解析 observer_ward 输出，详见 {raw_path}"

        stats = _analyze_entries(entries)
        updated = _update_fingerprint_state(out_dir, stats["records"])
        return _format_observer_summary(stats, raw_path, updated)
    except Exception as exc:
        return f"Error: {exc}"


def _sanitize_urls(urls):
    if not isinstance(urls, (list, tuple, set)):
        return []
    cleaned = []
    for value in urls:
        text = str(value or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def _build_screenshot_path(base_dir, target_url):
    parsed = urlparse(target_url)
    host = parsed.hostname or "unknown"
    port = parsed.port
    if not port:
        port = 443 if parsed.scheme == "https" else 80
    safe_host = re.sub(r"[^A-Za-z0-9_.-]", "_", host)
    filename = f"{safe_host}_{port}.png"
    return os.path.join(base_dir, filename)


def _count_js(page):
    try:
        dom_scripts = page.evaluate("() => document.scripts.length")
    except Exception:
        dom_scripts = 0
    try:
        resource_scripts = page.evaluate(
            "() => performance.getEntriesByType('resource')"
            ".filter(entry => (entry.name || '').toLowerCase().includes('.js')).length"
        )
    except Exception:
        resource_scripts = 0
    return int(dom_scripts or 0), int(resource_scripts or 0)


def _extract_favicon(page_url, page):
    try:
        href = page.evaluate(
            "() => {"
            " const node = document.querySelector('link[rel~=\"icon\"]');"
            " return node ? node.href : '';"
            "}"
        )
    except Exception:
        href = ""

    href = str(href or "").strip()
    if not href:
        return ""
    return urljoin(page_url, href)


def _extract_js_paths(page):
    try:
        scripts = page.evaluate(
            "() => Array.from(document.scripts).map(s => s.src).filter(src => src && src.length)"
        )
    except Exception:
        scripts = []

    items = []
    seen = set()
    for src in scripts or []:
        parsed = urlparse(src)
        path = parsed.path or parsed.netloc or src
        if not path:
            continue
        label = path if path.startswith("/") else f"/{path}"
        if label in seen:
            continue
        seen.add(label)
        items.append(f"JS:{label}")
        if len(items) >= 5:
            break
    return items


def _extract_feature_strings(html, js_paths):
    features = []
    for match in POWERED_BY_RE.findall(html):
        text = unescape(match)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            features.append(text)
    for match in COPYRIGHT_RE.findall(html):
        text = unescape(match)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            features.append(text)

    for item in js_paths:
        features.append(item)

    deduped = []
    seen = set()
    for feat in features:
        if feat in seen:
            continue
        seen.add(feat)
        deduped.append(feat)
        if len(deduped) >= 8:
            break
    return deduped


def _format_screenshot_results(records):
    lines = []
    for idx, record in enumerate(records, start=1):
        lines.append(f"{idx}. {record['url']}")
        if record.get("error"):
            lines.append(f"   Error: {record['error']}")
            continue
        lines.append(f"   Title: {record.get('title') or '(无title)'}")
        lines.append(f"   Screenshot: {record.get('screenshot')}")
        lines.append(
            f"   JS脚本: DOM={record.get('js_dom')} / Network={record.get('js_net')} "
            f"{'(有业务功能)' if record.get('has_js') else '(静态或JS缺失)'}"
        )
        if record.get("favicon"):
            lines.append(f"   Favicon: {record['favicon']}")
        if record.get("features"):
            lines.append(f"   特征: {', '.join(record['features'])}")
        else:
            lines.append("   特征: 无")
        if record.get("has_js"):
            lines.append("   标记: 有业务功能候选")
    return "\n".join(lines)


def screenshot(urls):
    try:
        targets = _sanitize_urls(urls)
        if not targets:
            return "Error: urls 列表为空"
        if len(targets) > 20:
            return "Error: 单次 screenshot 最多支持 20 个 URL"

        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            return "Error: 未安装 playwright，请先 pip install playwright 并执行 playwright install chromium"

        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)
        shot_dir = os.path.join(out_dir, "screenshots")
        os.makedirs(shot_dir, exist_ok=True)

        timeout = max(int(cfg.get("agent", {}).get("timeout", 60)), 45) * 1000
        records = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            try:
                for url in targets:
                    page = context.new_page()
                    page.set_default_timeout(timeout)
                    info = {"url": url}
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                        page.wait_for_timeout(1000)
                        screenshot_path = _build_screenshot_path(shot_dir, url)
                        page.screenshot(path=screenshot_path, full_page=True)
                        title = page.title()
                        js_dom, js_net = _count_js(page)
                        favicon = _extract_favicon(page.url, page)
                        js_paths = _extract_js_paths(page)
                        html = page.content()
                        features = _extract_feature_strings(html, js_paths)
                        info.update(
                            {
                                "title": title,
                                "screenshot": screenshot_path,
                                "js_dom": js_dom,
                                "js_net": js_net,
                                "has_js": (js_dom + js_net) > 0,
                                "favicon": favicon,
                                "features": features,
                            }
                        )
                    except Exception as exc:
                        info["error"] = str(exc)
                    finally:
                        page.close()
                    records.append(info)
            finally:
                try:
                    context.close()
                finally:
                    browser.close()

        return _format_screenshot_results(records)
    except Exception as exc:
        return f"Error: {exc}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "observer_ward",
            "description": "批量 Web 指纹识别，调用 observer_ward 并按价值分级，自动更新 state.json 的 fingerprints。",
            "parameters": {
                "type": "object",
                "properties": {
                    "targets": {
                        "type": "string",
                        "description": "URL 文件路径，例如 output/url.txt",
                    }
                },
                "required": ["targets"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "调用 Playwright 对指定 URL 截图，统计 JS、提取 favicon 和特征字符串，用于同源站发现。",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URL 列表（建议一次不超过20个）",
                    }
                },
                "required": ["urls"],
            },
        },
    },
]

FUNCTIONS = {"observer_ward": observer_ward, "screenshot": screenshot}
