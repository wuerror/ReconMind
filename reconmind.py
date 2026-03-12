import argparse
import json
import os
import time
from typing import Any, Dict, List

from openai import OpenAI

from config import load_config
from tools import STAGE_TOOLS, TOOL_FUNCTIONS


STAGES = ["company_info", "sensitive_info", "subdomain", "cyberspace", "fingerprint", "report"]
TOOL_OUTPUT_LIMIT = 4000
STAGE_START_INSTRUCTION = (
    "请开始执行本阶段任务。侦察工具通常会自动更新 output/state.json 中的 "
    "domains/subdomains/ips/urls/emails/fingerprints；你应优先通过 "
    'read_file("output/state.json") 查看最新状态。仅在 sensitive_findings 等少数字段需要补充时，'
    '才使用 write_file("output/state.json", ...) 手动写回。'
)

config = load_config()
MAX_ITER_PER_STAGE = int(config["agent"].get("max_iterations", 15))
LLM_RETRIES = int(config["agent"].get("llm_retries", 4))
LLM_TIMEOUT = int(config["agent"].get("llm_timeout", 120))
LLM_REASONING_EFFORT = str(config["llm"].get("reasoning_effort", "high")).strip().lower()
if LLM_REASONING_EFFORT not in {"low", "medium", "high"}:
    LLM_REASONING_EFFORT = "high"


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        val = value.strip().lower()
        if val in {"1", "true", "yes", "on"}:
            return True
        if val in {"0", "false", "no", "off"}:
            return False
    return default


LLM_STREAM = _as_bool(config["llm"].get("stream", True), default=True)
API_MODE = str(config["llm"].get("api_mode", "auto")).strip().lower()
if API_MODE not in {"auto", "responses", "chat"}:
    API_MODE = "auto"

RESPONSES_STREAM_ENABLED = LLM_STREAM
RESPONSES_REASONING_ENABLED = True
CHAT_REASONING_ENABLED = True

client = OpenAI(
    api_key=config["llm"]["api_key"],
    base_url=config["llm"]["base_url"],
    timeout=LLM_TIMEOUT,
)


def state_path() -> str:
    return os.path.join(config["agent"]["output_dir"], "state.json")


def load_state() -> dict:
    with open(state_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    os.makedirs(config["agent"]["output_dir"], exist_ok=True)
    with open(state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def init_state(company_name: str, domains=None, ips=None) -> dict:
    """初始化或加载已有 state（支持中断恢复）"""
    if os.path.exists(state_path()):
        print("[恢复] 检测到已有 state.json，从上次进度继续")
        return load_state()

    domains = domains or []
    ips = ips or []
    state = {
        "target": {
            "company_name": company_name,
            "known_domains": domains,
            "known_ips": ips,
        },
        "progress": {stage: "pending" for stage in STAGES},
        "results": {
            "domains": list(domains),
            "subdomains": [],
            "ips": list(ips),
            "urls": [],
            "emails": [],
            "fingerprints": {},
            "sensitive_findings": [],
        },
    }
    save_state(state)
    return state


def load_stage_prompt(stage_name: str) -> str:
    """加载共享前缀 + 阶段专属 prompt"""
    with open("prompts/shared_prefix.md", "r", encoding="utf-8") as f:
        prefix = f.read()
    with open(f"prompts/stage_{stage_name}.md", "r", encoding="utf-8") as f:
        stage = f.read()
    return prefix + "\n" + stage


def build_stage_context(stage_name: str, state: dict) -> str:
    """构建注入给 LLM 的当前状态摘要（不是完整 state，只给当前阶段需要的数据）"""
    target = state["target"]
    results = state["results"]
    context = f"目标公司: {target['company_name']}\n"

    if results["domains"]:
        context += f"已知域名: {', '.join(results['domains'])}\n"
    if results["ips"]:
        context += f"已知IP: {', '.join(results['ips'])}\n"
    if results["emails"]:
        context += f"已知邮箱: {', '.join(results['emails'])}\n"

    if stage_name in ("cyberspace", "fingerprint", "report") and results["subdomains"]:
        context += f"子域名数量: {len(results['subdomains'])} (详见 subdomain.txt)\n"
    if stage_name in ("fingerprint", "report") and results["urls"]:
        context += f"URL数量: {len(results['urls'])} (详见 url.txt)\n"

    return context


def truncate_output(result: str, tool_name: str) -> str:
    """截断过长的工具输出，完整结果存文件"""
    if len(result) <= TOOL_OUTPUT_LIMIT:
        return result

    out_dir = config["agent"]["output_dir"]
    os.makedirs(out_dir, exist_ok=True)
    index = len([name for name in os.listdir(out_dir) if name.startswith("raw_")])
    dump_path = os.path.join(out_dir, f"raw_{tool_name}_{index}.txt")

    with open(dump_path, "w", encoding="utf-8") as f:
        f.write(result)

    return result[:TOOL_OUTPUT_LIMIT] + f"\n... (共 {len(result)} 字符，完整结果已保存到 {dump_path})"


def _assistant_message_to_dict(message) -> dict:
    msg = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments or "{}",
                },
            }
            for tc in message.tool_calls
        ]
    return msg


def _obj_get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_plain(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_to_plain(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return _to_plain(obj.model_dump(exclude_none=True))
    if hasattr(obj, "to_dict"):
        return _to_plain(obj.to_dict())
    return obj


def _error_text(exc: Exception) -> str:
    return str(exc).lower()


def _safe_console_text(text: str) -> str:
    encoding = getattr(os.sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def _is_chat_unsupported_error(exc: Exception) -> bool:
    text = _error_text(exc)
    return (
        "unsupported legacy protocol" in text
        or "/v1/chat/completions is not supported" in text
        or "please use /v1/responses" in text
    )


def _is_responses_unsupported_error(exc: Exception) -> bool:
    text = _error_text(exc)
    return (
        "/v1/responses" in text
        and ("not supported" in text or "not found" in text or "unsupported" in text or "404" in text)
    )


def _is_retryable_error(exc: Exception) -> bool:
    name = exc.__class__.__name__
    if name in {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}:
        return True

    text = _error_text(exc)
    retry_markers = [
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "rate limit",
        "429",
        "500",
        "502",
        "503",
        "504",
        "upstream request failed",
    ]
    return any(marker in text for marker in retry_markers)


def _is_reasoning_unsupported_error(exc: Exception) -> bool:
    text = _error_text(exc)
    has_reasoning = (
        "reasoning_effort" in text
        or "reasoning.effort" in text
        or "reasoning" in text
        or "effort" in text
    )
    if not has_reasoning:
        return False
    return any(token in text for token in ["unknown", "unsupported", "not supported", "invalid", "unexpected"])


def _is_stream_unsupported_error(exc: Exception) -> bool:
    text = _error_text(exc)
    if "stream" not in text:
        return False
    return any(token in text for token in ["unknown", "unsupported", "not supported", "invalid", "unexpected"])


def _call_with_retry(func):
    delay = 1.0
    for attempt in range(LLM_RETRIES + 1):
        try:
            return func()
        except Exception as exc:
            if attempt < LLM_RETRIES and _is_retryable_error(exc):
                print(f"[LLM] 请求失败，{delay:.1f}s 后重试: {exc.__class__.__name__}")
                time.sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            raise


def _responses_stream_request(payload: Dict[str, Any]):
    with client.responses.stream(**payload) as stream:
        for _ in stream:
            pass
        return stream.get_final_response()


def _create_response(payload: Dict[str, Any]):
    global RESPONSES_STREAM_ENABLED, RESPONSES_REASONING_ENABLED

    while True:
        req = dict(payload)
        if RESPONSES_REASONING_ENABLED:
            req["reasoning"] = {"effort": LLM_REASONING_EFFORT}

        try:
            if RESPONSES_STREAM_ENABLED:
                return _call_with_retry(lambda: _responses_stream_request(req))
            return _call_with_retry(lambda: client.responses.create(**req))
        except Exception as exc:
            if RESPONSES_REASONING_ENABLED and _is_reasoning_unsupported_error(exc):
                RESPONSES_REASONING_ENABLED = False
                print("[LLM] 服务端不支持 reasoning 参数，已自动关闭")
                continue
            if RESPONSES_STREAM_ENABLED and _is_stream_unsupported_error(exc):
                RESPONSES_STREAM_ENABLED = False
                print("[LLM] 服务端不支持流式响应，已自动切换同步模式")
                continue
            raise


def _create_chat_completion(messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]):
    global CHAT_REASONING_ENABLED

    while True:
        req: Dict[str, Any] = {
            "model": config["llm"]["model"],
            "messages": messages,
            "tools": tools,
        }
        if CHAT_REASONING_ENABLED:
            req["reasoning_effort"] = LLM_REASONING_EFFORT

        try:
            return _call_with_retry(lambda: client.chat.completions.create(**req))
        except Exception as exc:
            if CHAT_REASONING_ENABLED and _is_reasoning_unsupported_error(exc):
                CHAT_REASONING_ENABLED = False
                print("[LLM] 当前 chat 接口不支持 reasoning_effort，已自动关闭")
                continue
            raise


def _run_tool(name: str, args: Dict[str, Any], step: int) -> str:
    print(f"  [{step}/{MAX_ITER_PER_STAGE}] {name}({json.dumps(args, ensure_ascii=True)[:100]})")

    if name not in TOOL_FUNCTIONS:
        result = f"Error: 未知工具 '{name}'"
    else:
        try:
            result = TOOL_FUNCTIONS[name](**args)
        except Exception as exc:
            result = f"Error: {exc}"

    return truncate_output(str(result), name)


def _to_responses_tools(chat_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted = []
    for tool in chat_tools:
        if tool.get("type") != "function":
            converted.append(tool)
            continue

        fn = tool.get("function")
        if not isinstance(fn, dict):
            converted.append(tool)
            continue

        converted.append(
            {
                "type": "function",
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
            }
        )
    return converted


def _extract_response_tool_calls(response) -> List[Dict[str, str]]:
    tool_calls: List[Dict[str, str]] = []
    for item in _obj_get(response, "output", []) or []:
        if _obj_get(item, "type") != "function_call":
            continue
        tool_calls.append(
            {
                "name": _obj_get(item, "name", ""),
                "arguments": _obj_get(item, "arguments", "") or "{}",
                "call_id": _obj_get(item, "call_id", "") or _obj_get(item, "id", ""),
            }
        )
    return tool_calls


def _extract_response_text(response) -> str:
    text = _obj_get(response, "output_text")
    if text:
        return text

    chunks: List[str] = []
    for item in _obj_get(response, "output", []) or []:
        if _obj_get(item, "type") != "message":
            continue
        for part in _obj_get(item, "content", []) or []:
            part_text = _obj_get(part, "text")
            if part_text:
                chunks.append(part_text)
    return "\n".join(chunks)


def _run_stage_chat(stage_name: str, stage_prompt: str, stage_context: str, tools: List[Dict[str, Any]]) -> dict:
    messages = [
        {"role": "system", "content": stage_prompt},
        {
            "role": "user",
            "content": stage_context + "\n" + STAGE_START_INSTRUCTION,
        },
    ]

    for i in range(MAX_ITER_PER_STAGE):
        response = _create_chat_completion(messages, tools)
        message = response.choices[0].message
        messages.append(_assistant_message_to_dict(message))

        if not message.tool_calls:
            snippet = message.content[:200] if message.content else "(无输出)"
            print(f"[{stage_name}] LLM 结束本阶段: {_safe_console_text(snippet)}")
            break

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args_raw = tool_call.function.arguments or "{}"
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}

            result = _run_tool(name, args, i + 1)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    else:
        print(f"[{stage_name}] 达到最大迭代次数 ({MAX_ITER_PER_STAGE})")

    return load_state()


def _run_stage_responses(stage_name: str, stage_prompt: str, stage_context: str, tools: List[Dict[str, Any]]) -> dict:
    history: List[Dict[str, Any]] = [
        {"role": "system", "content": stage_prompt},
        {
            "role": "user",
            "content": stage_context + "\n" + STAGE_START_INSTRUCTION,
        },
    ]
    response_tools = _to_responses_tools(tools)

    for i in range(MAX_ITER_PER_STAGE):
        payload = {
            "model": config["llm"]["model"],
            "input": history,
            "tools": response_tools,
        }
        response = _create_response(payload)

        response_items = [_to_plain(item) for item in (_obj_get(response, "output", []) or [])]
        tool_calls = _extract_response_tool_calls(response)

        if not tool_calls:
            content = _extract_response_text(response)
            snippet = content[:200] if content else "(无输出)"
            print(f"[{stage_name}] LLM 结束本阶段: {_safe_console_text(snippet)}")
            break

        history.extend(response_items)

        for tool_call in tool_calls:
            name = tool_call["name"]
            args_raw = tool_call["arguments"]
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}

            result = _run_tool(name, args, i + 1)
            call_id = tool_call["call_id"] or f"call_{i}_{name}"
            history.append({"type": "function_call_output", "call_id": call_id, "output": result})
    else:
        print(f"[{stage_name}] 达到最大迭代次数 ({MAX_ITER_PER_STAGE})")

    return load_state()


def run_stage(stage_name: str, state: dict) -> dict:
    """运行单个阶段的 agent loop，有独立的 messages"""
    print(f"\n{'=' * 60}")
    print(f"  阶段: {stage_name}")
    print(f"{'=' * 60}")

    stage_prompt = load_stage_prompt(stage_name)
    stage_context = build_stage_context(stage_name, state)
    tools = STAGE_TOOLS[stage_name]

    mode_order = {
        "auto": ["responses", "chat"],
        "responses": ["responses", "chat"],
        "chat": ["chat", "responses"],
    }[API_MODE]

    for idx, mode in enumerate(mode_order):
        try:
            if mode == "responses":
                return _run_stage_responses(stage_name, stage_prompt, stage_context, tools)
            return _run_stage_chat(stage_name, stage_prompt, stage_context, tools)
        except Exception as exc:
            has_next = idx < len(mode_order) - 1
            unsupported = (
                (mode == "responses" and _is_responses_unsupported_error(exc))
                or (mode == "chat" and _is_chat_unsupported_error(exc))
            )
            if has_next and unsupported:
                print(f"[{stage_name}] {mode} 协议不可用，自动切换到 {mode_order[idx + 1]}")
                continue
            raise

    raise RuntimeError(f"[{stage_name}] 无可用 LLM 协议")


def _has_nonempty_file(path: str) -> bool:
    return os.path.isfile(path) and os.path.getsize(path) > 0


def _validate_stage_artifacts(stage_name: str, state: dict) -> List[str]:
    out_dir = config["agent"]["output_dir"]
    results = state.get("results", {})
    errors: List[str] = []

    if stage_name == "report":
        report_path = os.path.join(out_dir, "target_report.md")
        if not os.path.isfile(report_path):
            errors.append(f"缺少报告文件: {report_path}")

    if stage_name in {"subdomain", "cyberspace", "fingerprint", "report"} and results.get("subdomains"):
        subdomain_path = os.path.join(out_dir, "subdomain.txt")
        if not _has_nonempty_file(subdomain_path):
            errors.append(
                f"state.results.subdomains 非空，但 {subdomain_path} 不存在或为空。"
            )

    if stage_name in {"cyberspace", "fingerprint", "report"} and results.get("urls"):
        url_path = os.path.join(out_dir, "url.txt")
        if not _has_nonempty_file(url_path):
            errors.append(
                f"state.results.urls 非空，但 {url_path} 不存在或为空。"
            )

    return errors


def _complete_stage_or_raise(stage_name: str, state: dict) -> None:
    errors = _validate_stage_artifacts(stage_name, state)
    if errors:
        state["progress"][stage_name] = "pending"
        save_state(state)
        detail = "\n".join(f"- {line}" for line in errors)
        raise RuntimeError(
            f"[校验失败] 阶段 {stage_name} 未满足完成条件:\n{detail}\n"
            "[提示] 修复对应输出后，重跑同一命令即可从未完成阶段继续。"
        )

    state["progress"][stage_name] = "completed"
    save_state(state)


def run_recon(company_name: str, domains=None, ips=None) -> None:
    state = init_state(company_name, domains, ips)

    for stage in STAGES:
        if state["progress"][stage] == "completed":
            print(f"[跳过] {stage} 已完成")
            continue

        domains_before = set(state["results"]["domains"])

        state["progress"][stage] = "in_progress"
        save_state(state)
        state = run_stage(stage, state)
        _complete_stage_or_raise(stage, state)

        if stage == "cyberspace":
            new_domains = set(state["results"]["domains"]) - domains_before
            if new_domains:
                print(f"\n[回溯] FOFA 发现 {len(new_domains)} 个新域名: {new_domains}")
                print("[回溯] 重新执行子域名收集")
                state["progress"]["subdomain"] = "in_progress"
                save_state(state)
                state = run_stage("subdomain", state)
                _complete_stage_or_raise("subdomain", state)

    print(f"\n{'=' * 60}")
    print("  ReconMind 完成")
    print(f"  报告: {config['agent']['output_dir']}/target_report.md")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ReconMind - 红队被动信息收集Agent")
    parser.add_argument("company", help="目标公司名称")
    parser.add_argument("-d", "--domains", nargs="*", help="已知域名", default=[])
    parser.add_argument("-i", "--ips", nargs="*", help="已知IP", default=[])
    parser.add_argument("--reset", action="store_true", help="清除已有state，重新开始")
    args = parser.parse_args()

    if args.reset and os.path.exists(state_path()):
        os.remove(state_path())
        print("[重置] 已清除旧 state")

    try:
        run_recon(args.company, args.domains, args.ips)
    except KeyboardInterrupt:
        print("\n[中断] 用户手动中断，当前进度已写入 state.json")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n[失败] 运行中断: {_safe_console_text(str(exc))}")
        print("[提示] 可直接重跑同一命令，程序会从 state.json 继续。")
        raise SystemExit(1)

