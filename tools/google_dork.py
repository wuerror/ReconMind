import textwrap


SLEEP_INTERVAL = 1.5  # googlesearch 内置节流，避免高频触发验证码


def _sanitize_query(query):
    if query is None:
        return ""
    return str(query).strip()


def _normalize_max_results(value):
    try:
        number = int(value)
    except Exception:
        number = 20
    return max(1, min(number, 50))


def _format_snippet(snippet):
    text = (snippet or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    return textwrap.shorten(text, width=220, placeholder="...")


def _coerce_result(entry):
    title = ""
    snippet = ""
    url = ""

    if isinstance(entry, str):
        url = entry.strip()
    elif isinstance(entry, dict):
        title = entry.get("title") or entry.get("name") or entry.get("text") or ""
        snippet = entry.get("description") or entry.get("snippet") or ""
        url = entry.get("url") or entry.get("link") or ""
    else:
        title = getattr(entry, "title", "") or getattr(entry, "name", "")
        snippet = getattr(entry, "description", "") or getattr(entry, "snippet", "")
        url = getattr(entry, "url", "") or getattr(entry, "link", "")

    title = (title or "").strip()
    snippet = _format_snippet(snippet)
    url = (url or "").strip()

    if not url:
        return None
    return {"title": title or "(无标题)", "url": url, "snippet": snippet}


def _web_search(query, max_results):
    try:
        from googlesearch import search
    except Exception:
        return None, "Error: 未安装 googlesearch-python，请先运行 pip install googlesearch-python"

    try:
        raw_results = search(query, num_results=max_results, sleep_interval=SLEEP_INTERVAL)
    except Exception as exc:
        return None, f"Error: googlesearch 查询失败: {exc}"

    items = []
    for entry in raw_results:
        parsed = _coerce_result(entry)
        if not parsed:
            continue
        items.append(parsed)
        if len(items) >= max_results:
            break

    return items, None


def _format_results(query, results):
    lines = [
        f"Google Dork: {query}",
        f"数据源: googlesearch-python (sleep_interval={SLEEP_INTERVAL}s)",
        f"返回 {len(results)} 条结果",
    ]

    for idx, item in enumerate(results, start=1):
        lines.append(f"{idx}. {item['title']}")
        lines.append(f"   URL: {item['url']}")
        if item["snippet"]:
            lines.append(f"   摘要: {item['snippet']}")

    return "\n".join(lines)


def google_dork(query, max_results=20):
    try:
        q = _sanitize_query(query)
        if not q:
            return "Error: query is required"

        limit = _normalize_max_results(max_results)
        results, error = _web_search(q, limit)
        if error:
            return error

        if not results:
            return f"Google Dork: {q}\ngooglesearch-python 未返回结果"

        return _format_results(q, results)
    except Exception as exc:
        return f"Error: {exc}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "google_dork",
            "description": "Google Dork 搜索（直接调用 googlesearch-python，并控制访问节奏）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Google 搜索语句"},
                    "max_results": {
                        "type": "integer",
                        "description": "返回条数上限，默认20，最大50",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        },
    }
]

FUNCTIONS = {"google_dork": google_dork}
