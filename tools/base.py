import os
import subprocess

from config import load_config


def _get_timeout() -> int:
    try:
        cfg = load_config()
        return int(cfg["agent"].get("timeout", 60))
    except Exception:
        return 60


def bash(command: str) -> str:
    """Execute a shell command with timeout from config."""
    if not command:
        return "Error: command is required"

    timeout = _get_timeout()

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: failed to execute command: {e}"

    chunks = []
    if proc.stdout:
        chunks.append(f"[stdout]\n{proc.stdout}")
    if proc.stderr:
        chunks.append(f"[stderr]\n{proc.stderr}")
    chunks.append(f"[exit_code] {proc.returncode}")
    return "\n".join(chunks)


def read_file(path: str) -> str:
    """Read file content as UTF-8 text."""
    if not path:
        return "Error: path is required"

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error: failed to read file '{path}': {e}"


def write_file(path: str, content: str) -> str:
    """Write UTF-8 text to file, creating parent directories if needed."""
    if not path:
        return "Error: path is required"

    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"Error: failed to write file '{path}': {e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a shell command and return stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of file to read.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text content to a file on disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of file to write.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]

FUNCTIONS = {
    "bash": bash,
    "read_file": read_file,
    "write_file": write_file,
}
