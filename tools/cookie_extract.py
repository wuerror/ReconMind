import os

import yaml

from config import load_config


PLATFORM_LOGIN = {
    "aiqicha": {
        "login_url": "https://aiqicha.baidu.com",
        "username_selector": "input[type='text']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit']",
        "cookie_key": "aiqicha",
    },
    "tianyancha": {
        "login_url": "https://www.tianyancha.com/login",
        "username_selector": "input[type='text']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit']",
        "cookie_key": "tianyancha",
    },
    "qimai": {
        "login_url": "https://www.qimai.cn/account/signin",
        "username_selector": "input[name='mobile'], input[type='text']",
        "password_selector": "input[name='password'], input[type='password']",
        "submit_selector": "button[type='submit'], .signin-btn",
        "cookie_key": "qimai",
    },
}

COOKIE_VALIDATORS = {
    "aiqicha": lambda cookies: any(c.get("name") == "BDUSS" for c in cookies),
    "tianyancha": lambda cookies: any(c.get("name") == "auth_token" for c in cookies),
    "qimai": lambda cookies: any(str(c.get("name", "")).startswith("qm_") for c in cookies),
}


def _get_enscan_config_path(cfg):
    tool_path = str(cfg.get("tools", {}).get("enscan_path", "") or "").strip()
    if not tool_path:
        return os.path.abspath(os.path.join("bin", "ENScan_GO", "config.yaml"))

    abs_path = os.path.abspath(tool_path)
    if os.path.isdir(abs_path):
        return os.path.join(abs_path, "config.yaml")
    return os.path.join(os.path.dirname(abs_path), "config.yaml")


def _cookie_text(cookies):
    pairs = []
    for item in cookies:
        name = str(item.get("name", "") or "").strip()
        value = str(item.get("value", "") or "")
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _has_credentials(platform_cred):
    if not isinstance(platform_cred, dict):
        return False
    username = str(platform_cred.get("username", "") or "").strip()
    password = str(platform_cred.get("password", "") or "").strip()
    return bool(username and password)


def update_enscan_config(config_path, results):
    try:
        if not os.path.isfile(config_path):
            return f"Error: ENScan config not found: {config_path}"

        with open(config_path, "r", encoding="utf-8") as f:
            enscan_cfg = yaml.safe_load(f) or {}

        cookies_cfg = enscan_cfg.get("cookies")
        if not isinstance(cookies_cfg, dict):
            cookies_cfg = {}
            enscan_cfg["cookies"] = cookies_cfg

        updated = 0
        for platform, item in results.items():
            if not isinstance(item, dict):
                continue
            status = item.get("status")
            cookies = item.get("cookies") or []
            if status not in {"success", "cached"} or not cookies:
                continue
            cookie_key = PLATFORM_LOGIN.get(platform, {}).get("cookie_key", platform)
            cookie_text = _cookie_text(cookies)
            if not cookie_text:
                continue
            cookies_cfg[cookie_key] = cookie_text
            updated += 1

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(enscan_cfg, f, allow_unicode=True, sort_keys=False)

        return f"updated {updated} platform cookies"
    except Exception as e:
        return f"Error: {e}"


def get_empty_cookie_platforms():
    try:
        cfg = load_config()
        enscan_config_path = _get_enscan_config_path(cfg)
        if not os.path.isfile(enscan_config_path):
            return []

        with open(enscan_config_path, "r", encoding="utf-8") as f:
            enscan_cfg = yaml.safe_load(f) or {}

        cookies = enscan_cfg.get("cookies", {})
        if not isinstance(cookies, dict):
            return []

        empty = []
        for platform, value in cookies.items():
            if not str(value or "").strip():
                empty.append(str(platform))
        return empty
    except Exception:
        return []


def format_summary(results):
    lines = []
    for platform, item in results.items():
        status = item.get("status", "error")
        if status == "success":
            lines.append(f"[Cookie] {platform}: ✓ 成功（自动登录）")
        elif status == "cached":
            lines.append(f"[Cookie] {platform}: ✓ 成功（缓存复用）")
        elif status == "failed":
            lines.append(f"[Cookie] {platform}: ⚠ 失败（可能需要验证码）")
        elif status == "skipped":
            lines.append(f"[Cookie] {platform}: - 跳过（未配置凭据）")
        else:
            detail = str(item.get("error", "") or "").strip()
            if detail:
                lines.append(f"[Cookie] {platform}: ✗ 错误（{detail}）")
            else:
                lines.append(f"[Cookie] {platform}: ✗ 错误")
    return "\n".join(lines)


def refresh_cookies(platforms=None):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return f"Error: Playwright not available: {e}"

    try:
        cfg = load_config()
        credentials = cfg.get("credentials", {})
        if not isinstance(credentials, dict):
            credentials = {}

        output_dir = cfg.get("agent", {}).get("output_dir", "./output")
        os.makedirs(output_dir, exist_ok=True)
        user_data_dir = os.path.join(output_dir, ".browser_profile")
        os.makedirs(user_data_dir, exist_ok=True)

        enscan_config_path = _get_enscan_config_path(cfg)
        targets = platforms or list(PLATFORM_LOGIN.keys())

        results = {}
        playwright_manager = None
        browser = None
        try:
            playwright_manager = sync_playwright().start()
            browser = playwright_manager.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                locale="zh-CN",
            )

            for platform in targets:
                adapter = PLATFORM_LOGIN.get(platform)
                if not adapter:
                    results[platform] = {"status": "error", "error": "unsupported platform"}
                    continue

                platform_cred = credentials.get(platform, {})
                if not _has_credentials(platform_cred):
                    results[platform] = {"status": "skipped", "cookies": []}
                    continue

                username = str(platform_cred.get("username", "") or "")
                password = str(platform_cred.get("password", "") or "")
                login_url = adapter["login_url"]
                validator = COOKIE_VALIDATORS.get(platform, lambda cookie_items: False)

                page = browser.new_page()
                try:
                    page.goto(login_url, wait_until="networkidle")

                    current_cookies = page.context.cookies([login_url])
                    if validator(current_cookies):
                        results[platform] = {"status": "cached", "cookies": current_cookies}
                        continue

                    page.fill(adapter["username_selector"], username)
                    page.fill(adapter["password_selector"], password)
                    page.click(adapter["submit_selector"])
                    page.wait_for_timeout(3000)

                    refreshed_cookies = page.context.cookies([login_url])
                    if validator(refreshed_cookies):
                        results[platform] = {"status": "success", "cookies": refreshed_cookies}
                    else:
                        results[platform] = {"status": "failed", "cookies": []}
                except Exception as e:
                    results[platform] = {"status": "error", "error": str(e), "cookies": []}
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright_manager is not None:
                try:
                    playwright_manager.stop()
                except Exception:
                    pass

        update_result = update_enscan_config(enscan_config_path, results)
        summary = format_summary(results)
        if str(update_result).startswith("Error:"):
            return f"{summary}\n{update_result}"
        return f"{summary}\n[Cookie] ENScan 配置已更新: {enscan_config_path}"
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "refresh_cookies",
            "description": "Playwright 自动登录并提取企业情报平台 Cookie，写入 ENScan 配置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platforms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选，指定需要刷新的平台列表",
                    }
                },
                "required": [],
            },
        },
    }
]

FUNCTIONS = {"refresh_cookies": refresh_cookies}


