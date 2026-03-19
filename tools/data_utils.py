import os


VALID_TYPES = {"subdomain", "url", "ip"}


def _normalize_value(value, data_type):
    text = str(value or "").strip()
    if not text:
        return ""
    if data_type in {"subdomain", "url"}:
        return text.lower()
    return text


def _read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned:
                yield cleaned


def dedup_merge(input_files, output_file, data_type):
    try:
        if not input_files:
            return "Error: input_files 不能为空"
        if not output_file:
            return "Error: output_file 不能为空"

        normalized_type = str(data_type or "").strip().lower()
        if normalized_type not in VALID_TYPES:
            return "Error: data_type 仅支持 subdomain/url/ip"

        files = [str(p).strip() for p in input_files if str(p).strip()]
        if not files:
            return "Error: input_files 不能为空"

        seen = set()
        unique_values = []
        total = 0

        for path in files:
            if not os.path.isfile(path):
                return f"Error: 输入文件不存在: {path}"
            try:
                for line in _read_lines(path):
                    total += 1
                    value = _normalize_value(line, normalized_type)
                    if not value or value in seen:
                        continue
                    seen.add(value)
                    unique_values.append(value)
            except Exception as exc:
                return f"Error: 读取文件失败 {path}: {exc}"

        parent = os.path.dirname(output_file)
        if parent:
            os.makedirs(parent, exist_ok=True)

        try:
            with open(output_file, "w", encoding="utf-8") as f:
                for value in unique_values:
                    f.write(value + "\n")
        except Exception as exc:
            return f"Error: 写入输出文件失败 {output_file}: {exc}"

        return f"合并 {total} 条 → 去重后 {len(unique_values)} 条，已写入 {output_file}"
    except Exception as exc:
        return f"Error: {exc}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "dedup_merge",
            "description": "合并多个结果文件并去重，支持 subdomain/url/ip。",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "输入文件列表",
                    },
                    "output_file": {"type": "string", "description": "输出文件路径"},
                    "data_type": {
                        "type": "string",
                        "description": "数据类型：subdomain/url/ip",
                    },
                },
                "required": ["input_files", "output_file", "data_type"],
            },
        },
    }
]

FUNCTIONS = {"dedup_merge": dedup_merge}
