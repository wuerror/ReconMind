import base64
import json
import os
import re

import requests

from config import load_config


HIGH_VALUE_KEYWORDS = [
    "登录",
    "admin",
    "管理",
    "后台",
    "系统",
    "平台",
    "jenkins",
    "gitlab",
    "jira",
    "zabbix",
    "grafana",
    "nacos",
    "apollo",
    "swagger",
    "actuator",
    "druid",
    "oa",
    "erp",
    "crm",
    "sso",
    "vpn",
    "minio",
    "harbor",
    "rabbitmq",
    "elasticsearch",
    "spring boot",
    "shiro",
    "weblogic",
    "jboss",
    "struts",
    "phpmyadmin",
    "adminer",
]

DOMAIN_RE = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}\b",
    re.IGNORECASE,
)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


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


def _is_high_value(title, port):
    title_lower = str(title or "").lower()
    if any(kw in title_lower for kw in HIGH_VALUE_KEYWORDS):
        return True

    try:
        if int(str(port)) not in (80, 443):
            return True
    except Exception:
        pass

    return False


def _normalize_size(size, fields):
    try:
        value = int(size)
    except Exception:
        value = 500

    value = max(1, min(value, 10000))

    fields_lower = str(fields or "").lower()
    if ("cert" in fields_lower or "banner" in fields_lower) and value > 2000:
        value = 2000

    return value


def _extract_domains(text):
    if not text:
        return []
    return sorted({d.lower() for d in DOMAIN_RE.findall(str(text))})


def _extract_ips(text):
    if not text:
        return []

    ips = set()
    for ip in IP_RE.findall(str(text)):
        parts = ip.split(".")
        if len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts):
            ips.add(ip)
    return sorted(ips)


def _clip(text, limit):
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _build_summary(
    query,
    total,
    fetched,
    added_domains,
    added_ips,
    added_urls,
    high_value,
    mid_count,
    low_count,
    raw_path,
):
    domain_list = "、".join(added_domains) if added_domains else "无"

    detail_lines = []
    for idx, item in enumerate(high_value[:15], 1):
        detail_lines.append(
            f"{idx}. URL={_clip(item['url'], 56)} | 端口={item['port']} | Title={_clip(item['title'], 38)}"
        )

    selected_count = len(detail_lines)
    while True:
        lines = [
            "统计概览",
            f"查询: {query}",
            f"FOFA总数 {total} 条，本次获取 {fetched} 条",
            f"新增 {len(added_domains)} 域名 / {len(added_ips)} 个IP / {len(added_urls)} 个URL",
            f"原始结果: {raw_path}",
            "",
            f"新发现域名 ({len(added_domains)})",
            domain_list,
            "",
            f"高价值目标详情 ({len(high_value)}，最多15条)",
        ]

        if selected_count > 0:
            lines.extend(detail_lines[:selected_count])
            hidden = len(high_value) - selected_count
            if hidden > 0:
                lines.append(f"... 另有 {hidden} 条高价值目标未展开")
        else:
            lines.append("无")

        lines.append("")
        lines.append(f"中价值目标数量: {mid_count}")
        lines.append(f"低价值目标数量: {low_count}")

        summary = "\n".join(lines)
        if len(summary) <= 1000 or selected_count == 0:
            break
        selected_count -= 1

    return summary


def fofa_query(query, fields="host,ip,port,domain,title,protocol,link", size=500):
    try:
        if not query or not str(query).strip():
            return "Error: query is required"

        cfg = load_config()
        out_dir = _ensure_output_dir(cfg)
        key = cfg.get("api_keys", {}).get("fofa_key", "")
        if not key:
            return "Error: missing api_keys.fofa_key in config.yaml"

        fields = str(fields or "host,ip,port,domain,title,protocol,link")
        size = _normalize_size(size, fields)

        qbase64 = base64.b64encode(str(query).encode("utf-8")).decode("utf-8")
        api_url = "https://fofa.info/api/v1/search/all"
        params = {
            "key": key,
            "qbase64": qbase64,
            "fields": fields,
            "size": size,
        }

        try:
            resp = requests.get(api_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return f"Error: FOFA query failed: {e}"

        if data.get("error"):
            return f"Error: FOFA API error: {data.get('errmsg', 'unknown error')}"

        results = data.get("results", [])
        total = data.get("size", len(results))

        raw_path = _next_raw_path(out_dir, "fofa")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        field_names = [x.strip() for x in fields.split(",") if x.strip()]
        found_domains = set()
        found_ips = set()
        found_urls = set()

        high_value = []
        mid_count = 0
        low_count = 0

        for row in results:
            if not isinstance(row, list):
                continue

            item = dict(zip(field_names, row))
            title = str(item.get("title", "") or "").strip()
            port = str(item.get("port", "") or "").strip()
            host = str(item.get("host", "") or "").strip()
            link = str(item.get("link", "") or "").strip()
            domain_field = item.get("domain", "")
            ip_field = item.get("ip", "")

            for d in _extract_domains(domain_field):
                found_domains.add(d)
            for ip in _extract_ips(ip_field):
                found_ips.add(ip)
            if link:
                found_urls.add(link)

            display_url = link or host or "(unknown)"

            if _is_high_value(title, port):
                high_value.append(
                    {
                        "url": display_url,
                        "port": port or "-",
                        "title": title or "(无title)",
                    }
                )
            elif title or display_url != "(unknown)" or port:
                mid_count += 1
            else:
                low_count += 1

        state, state_path = _load_state(out_dir)
        results_state = state["results"]

        added_domains = _append_unique(results_state["domains"], sorted(found_domains))
        added_ips = _append_unique(results_state["ips"], sorted(found_ips))
        added_urls = _append_unique(results_state["urls"], sorted(found_urls))
        _save_state(state, state_path)

        return _build_summary(
            query=str(query),
            total=total,
            fetched=len(results),
            added_domains=added_domains,
            added_ips=added_ips,
            added_urls=added_urls,
            high_value=high_value,
            mid_count=mid_count,
            low_count=low_count,
            raw_path=raw_path,
        )
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fofa_query",
            "description": "FOFA网络空间搜索。自动提取域名/IP/URL并更新state.json。返回分层摘要（新域名列表 + 高价值目标详情 + 统计）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "FOFA查询语句，如 domain=\"target.com\"",
                    },
                    "fields": {
                        "type": "string",
                        "description": "返回字段",
                        "default": "host,ip,port,domain,title,protocol,link",
                    },
                    "size": {
                        "type": "integer",
                        "description": "返回条数上限，默认500，最大10000",
                        "default": 500,
                    },
                },
                "required": ["query"],
            },
        },
    }
]

FUNCTIONS = {"fofa_query": fofa_query}
