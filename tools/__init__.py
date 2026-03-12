from .base import TOOLS as BASE_TOOLS, FUNCTIONS as BASE_FUNCTIONS
from .enscan import TOOLS as ENSCAN_TOOLS, FUNCTIONS as ENSCAN_FUNCTIONS
from .subdomain import TOOLS as SUB_TOOLS, FUNCTIONS as SUB_FUNCTIONS
from .fofa import TOOLS as FOFA_TOOLS, FUNCTIONS as FOFA_FUNCTIONS
from .google_dork import TOOLS as GOOGLE_TOOLS, FUNCTIONS as GOOGLE_FUNCTIONS
from .github_search import TOOLS as GITHUB_TOOLS, FUNCTIONS as GITHUB_FUNCTIONS
from .fingerprint import TOOLS as FP_TOOLS, FUNCTIONS as FP_FUNCTIONS
from .data_utils import TOOLS as DATA_TOOLS, FUNCTIONS as DATA_FUNCTIONS


# 每个阶段可用的工具集合：基础工具 + 阶段专属工具
STAGE_TOOLS = {
    "company_info": BASE_TOOLS + ENSCAN_TOOLS,
    "sensitive_info": BASE_TOOLS + GOOGLE_TOOLS + GITHUB_TOOLS,
    "subdomain": BASE_TOOLS + SUB_TOOLS + DATA_TOOLS,
    "cyberspace": BASE_TOOLS + FOFA_TOOLS + DATA_TOOLS,
    "fingerprint": BASE_TOOLS + FP_TOOLS,
    "report": BASE_TOOLS,
}


# 全局函数注册表（执行时查找）
TOOL_FUNCTIONS = {}
for funcs in [
    BASE_FUNCTIONS,
    ENSCAN_FUNCTIONS,
    SUB_FUNCTIONS,
    FOFA_FUNCTIONS,
    GOOGLE_FUNCTIONS,
    GITHUB_FUNCTIONS,
    FP_FUNCTIONS,
    DATA_FUNCTIONS,
]:
    TOOL_FUNCTIONS.update(funcs)
