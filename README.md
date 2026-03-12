# ReconMind

ReconMind 是一个面向红队被动信息收集的多阶段 Agent。  
当前仓库定位为 **P0 可运行骨架**：阶段编排、状态管理、基础工具、Prompt 拆分与断点恢复。

## 当前能力（P0）

- 阶段编排：`company_info -> sensitive_info -> subdomain -> cyberspace -> fingerprint -> report`
- 状态管理：`output/state.json`（支持中断恢复）
- 状态契约（design-sync）：
  - 侦察工具设计上应自动更新 `output/state.json`
  - LLM 默认通过 `read_file("output/state.json")` 读取最新状态
  - 仅少数字段（尤其 `sensitive_findings`）建议手动 `write_file` 回写
- 基础工具：
  - `bash`
  - `read_file`
  - `write_file`
- Prompt 组织：`prompts/shared_prefix.md` + 各阶段 `prompts/stage_*.md`
- 轻量完成判定（代码侧）：
  - `report` 阶段结束后检查 `output/target_report.md` 是否存在
  - 当 `state.results.subdomains` 非空时，检查 `output/subdomain.txt` 非空
  - 当 `state.results.urls` 非空时，检查 `output/url.txt` 非空
- 协议兼容：
  - 优先 `responses`，自动兼容部分站点
  - 支持可选流式调用和推理强度配置

## 占位能力说明（当前未实现）

以下模块目前仍是 placeholder，不提供真实侦察能力：

- `tools/enscan.py`
- `tools/subdomain.py`
- `tools/fofa.py`
- `tools/google_dork.py`
- `tools/github_search.py`
- `tools/fingerprint.py`
- `tools/data_utils.py`

P0 只保证 orchestrator、state、prompt、基础工具和恢复机制可运行；不宣称以上侦察能力已可用。

## 项目结构

```text
ReconMind/
├── reconmind.py
├── config.py
├── config.yaml
├── prompts/
├── tools/
├── output/
├── requirements.txt
└── README.md
```

## 安装

```bash
pip install -r requirements.txt
```

## 配置

编辑 `config.yaml`：

- `llm.api_key`
- `llm.base_url`
- `llm.model`

可选项：

- `llm.api_mode`: `auto | responses | chat`
- `llm.stream`: `true | false`
- `llm.reasoning_effort`: `low | medium | high`
- `agent.llm_retries`
- `agent.llm_timeout`

也可用环境变量覆盖：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_API_MODE`
- `OPENAI_STREAM`
- `OPENAI_REASONING_EFFORT`

## 运行

```bash
# 基本运行
python reconmind.py "某某科技有限公司"

# 带已知域名/IP
python reconmind.py "某某科技有限公司" -d target.com -i 1.2.3.4

# 清理旧状态并重跑
python reconmind.py "某某科技有限公司" -d target.com --reset
```

## 断点恢复

程序会优先读取 `output/state.json`。如果存在已完成阶段，会自动跳过并从未完成阶段继续。

## 安全建议

- 不要将真实密钥提交到仓库。
- 建议通过环境变量注入生产密钥。
- 若密钥曾暴露，立即轮换。
