import subprocess


def run_external(cmd_args, timeout=120):
    try:
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"Error: command timed out after {timeout}s"
    except FileNotFoundError:
        return None, f"Error: command not found: {cmd_args[0] if cmd_args else ''}"
    except Exception as e:
        return None, f"Error: command execution failed: {e}"

    if result.returncode == 0:
        return result, None

    help_text = ""
    try:
        help_result = subprocess.run(
            [cmd_args[0], "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        help_text = (help_result.stdout or help_result.stderr or "")[:1500]
    except Exception:
        help_text = ""

    stderr = (result.stderr or "").strip()
    if not stderr:
        stderr = (result.stdout or "").strip()
    error = f"Error (exit code {result.returncode}): {stderr}"
    if help_text:
        error += f"\n\n工具用法参考:\n{help_text}"
    return None, error
