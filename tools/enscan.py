import json
import os
import re
import shlex
import shutil

from config import load_config
from .utils import run_external


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DOMAIN_RE = re.compile(
    r"(?<!@)\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}\b",
    re.IGNORECASE,
)
COMPANY_KEYWORDS = [
    "有限公司",
    "有限责任公司",
    "股份有限公司",
    "集团",
    "公司",
    "Co.,",
    "Ltd",
    "Inc",
    "LLC",
    "Corp",
]


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


def _resolve_tool_path(tool_path):
    if not tool_path:
        return None, "Error: ENScan path is empty in config.yaml (tools.enscan_path)"

    if os.path.sep in tool_path or "/" in tool_path:
        abs_path = os.path.abspath(tool_path)
        if not os.path.exists(abs_path):
            return None, f"Error: ENScan tool not found: {tool_path}"
        return abs_path, None

    found = shutil.which(tool_path)
    if not found:
        return None, f"Error: ENScan tool not found in PATH: {tool_path}"
    return found, None


def _clean_table_line(line):
    cleaned = line.strip()
    if not cleaned:
        return ""
    border_chars = set("+-=|┌┐└┘├┤┬┴┼─━")
    if all(ch in border_chars for ch in cleaned):
        return ""
    return cleaned


def _looks_like_company(text):
    return any(k in text for k in COMPANY_KEYWORDS)


def _parse_enscan_output(text):
    companies = set()
    domains = set()
    emails = set()

    for raw_line in text.splitlines():
        line = _clean_table_line(raw_line)
        if not line:
            continue

        for email in EMAIL_RE.findall(line):
            emails.add(email.lower())

        for domain in DOMAIN_RE.findall(line):
            domains.add(domain.lower())

        if _looks_like_company(line):
            parts = re.split(r"\s{2,}|\t|\|", line)
            for part in parts:
                candidate = part.strip().strip("[]")
                if len(candidate) < 4:
                    continue
                if EMAIL_RE.search(candidate) or DOMAIN_RE.search(candidate):
                    continue
                if _looks_like_company(candidate):
                    companies.add(candidate)

    return sorted(companies), sorted(domains), sorted(emails)


def enscan(company_name, options=""):
    try:
        if not company_name or not str(company_name).strip():
            return "Error: company_name is required"

        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)
        timeout = max(_timeout(cfg), 180)

        tool_path = cfg.get("tools", {}).get("enscan_path", "")
        cmd_bin, err = _resolve_tool_path(tool_path)
        if err:
            return err

        extra_args = []
        if options and str(options).strip():
            try:
                extra_args = shlex.split(str(options), posix=False)
            except Exception:
                extra_args = str(options).split()

        cmd = [cmd_bin, "-n", str(company_name).strip()] + extra_args
        result, error = run_external(cmd, timeout=timeout)
        if error:
            return error

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        raw_text = f"{stdout}\n{stderr}".strip() if stderr else stdout

        raw_path = _next_raw_path(out_dir, "enscan")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        companies, domains, emails = _parse_enscan_output(raw_text)
        suffixes = sorted({e.split("@", 1)[1] for e in emails if "@" in e})

        state, state_path = _load_state(out_dir)
        results = state["results"]
        added_domains = _append_unique(results["domains"], domains)
        added_emails = _append_unique(results["emails"], emails)
        _save_state(state, state_path)

        domain_text = "、".join(domains) if domains else "无"
        suffix_text = "、".join(suffixes) if suffixes else "无"

        return (
            f"发现 {len(companies)} 个关联公司、{len(domains)} 个备案域名（{domain_text}）、"
            f"{len(suffixes)} 个邮箱后缀（{suffix_text}）\n"
            f"新增域名 {len(added_domains)} 个，新增邮箱 {len(added_emails)} 个，"
            f"已更新 state.json，原始输出: {raw_path}"
        )
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "enscan",
            "description": "查询企业信息。自动解析结果并更新state.json(domains/emails字段)。返回发现摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "目标公司名称"},
                    "options": {
                        "type": "string",
                        "description": "附加参数，如 -invest 查询投资关系",
                        "default": "",
                    },
                },
                "required": ["company_name"],
            },
        },
    }
]

FUNCTIONS = {"enscan": enscan}
