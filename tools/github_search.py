import re
import time

import requests

from config import load_config


VALID_TYPES = {"code", "repositories", "commits"}


def _clean_keyword(keyword):
    if keyword is None:
        return ""
    return str(keyword).strip()


def _normalize_search_type(value):
    if not value:
        return "code"
    candidate = str(value).strip().lower()
    if candidate not in VALID_TYPES:
        return "code"
    return candidate


def _collapse_snippet(snippet):
    if not snippet:
        return ""
    text = snippet.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 220:
        return text[:217] + "..."
    return text


def _rate_limit_wait(reset_header):
    try:
        reset_epoch = int(reset_header)
        wait = int(reset_epoch - time.time())
        return max(wait, 0)
    except Exception:
        return 60


def _format_code_item(idx, item):
    repo = ""
    repository = item.get("repository")
    if isinstance(repository, dict):
        repo = repository.get("full_name") or repository.get("name") or ""
    repo = repo or "(unknown repo)"

    path = item.get("path") or ""
    url = item.get("html_url") or item.get("url") or ""

    snippet = ""
    matches = item.get("text_matches") or []
    for match in matches:
        fragment = match.get("fragment")
        if fragment:
            snippet = _collapse_snippet(fragment)
            break

    if not snippet:
        snippet = _collapse_snippet(item.get("summary") or "")

    lines = [
        f"{idx}. {repo} :: {path}",
        f"   URL: {url}",
    ]
    if snippet:
        lines.append(f"   代码片段: {snippet}")
    return "\n".join(lines)


def _format_repo_item(idx, item):
    full_name = item.get("full_name") or item.get("name") or "(unknown)"
    desc = _collapse_snippet(item.get("description"))
    stars = item.get("stargazers_count")
    url = item.get("html_url") or item.get("url") or ""
    lines = [f"{idx}. {full_name} ⭐{stars or 0}", f"   URL: {url}"]
    if desc:
        lines.append(f"   描述: {desc}")
    return "\n".join(lines)


def _format_commit_item(idx, item):
    repository = item.get("repository") or {}
    repo_name = repository.get("full_name") or repository.get("name") or "(unknown repo)"
    commit = item.get("commit") or {}
    message = commit.get("message") or ""
    message_line = message.splitlines()[0] if message else ""
    author = (commit.get("author") or {}).get("name") or ""
    url = item.get("html_url") or item.get("url") or ""
    lines = [
        f"{idx}. {repo_name} :: {author or 'unknown author'}",
        f"   提交: {message_line or '(无提交信息)'}",
        f"   URL: {url}",
    ]
    return "\n".join(lines)


def _format_items(search_type, items, total, keyword):
    header = [
        f"GitHub Search [{search_type}] - 关键词: {keyword}",
        f"接口返回: 共 {total} 条，本页 {len(items)} 条",
    ]
    if not items:
        header.append("暂无结果。")
        return "\n".join(header)

    lines = list(header)
    for idx, item in enumerate(items, start=1):
        if search_type == "repositories":
            lines.append(_format_repo_item(idx, item))
        elif search_type == "commits":
            lines.append(_format_commit_item(idx, item))
        else:
            lines.append(_format_code_item(idx, item))
    return "\n".join(lines)


def github_search(keyword, search_type="code"):
    try:
        kw = _clean_keyword(keyword)
        if not kw:
            return "Error: keyword is required"

        stype = _normalize_search_type(search_type)
        cfg = load_config()
        token = (cfg.get("api_keys", {}).get("github_token") or "").strip()
        if not token:
            return "Error: 缺少 config.yaml 中的 api_keys.github_token"

        url = f"https://api.github.com/search/{stype}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.text-match+json",
            "User-Agent": "ReconMind-Agent",
        }
        params = {"q": kw}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=25)
        except Exception as exc:
            return f"Error: GitHub API 请求失败: {exc}"

        if resp.status_code == 403:
            wait_seconds = _rate_limit_wait(resp.headers.get("X-RateLimit-Reset"))
            return f"GitHub API 限速，请等待 {wait_seconds} 秒后重试"

        if resp.status_code != 200:
            try:
                data = resp.json()
                message = data.get("message", resp.text.strip())
            except Exception:
                message = resp.text.strip() or "unknown error"
            return f"Error: GitHub API 请求失败 ({resp.status_code}): {message}"

        data = resp.json()
        items = data.get("items") or []
        total = data.get("total_count", len(items))

        return _format_items(stype, items, total, kw)
    except Exception as exc:
        return f"Error: {exc}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_search",
            "description": "GitHub 信息泄露搜索。支持 code/repositories/commits。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键字"},
                    "search_type": {
                        "type": "string",
                        "description": "搜索类型：code/repositories/commits，默认code",
                        "default": "code",
                    },
                },
                "required": ["keyword"],
            },
        },
    }
]

FUNCTIONS = {"github_search": github_search}
