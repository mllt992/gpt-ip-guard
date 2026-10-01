"""Block chatgpt.com / openai.com via hosts file."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

MARK_BEGIN = "# GPT-IP-GUARD BEGIN"
MARK_END = "# GPT-IP-GUARD END"

BLOCK_HOSTS = [
    "chatgpt.com",
    "www.chatgpt.com",
    "openai.com",
    "www.openai.com",
    "api.openai.com",
    "chat.openai.com",
    "ab.chatgpt.com",
    "auth0.openai.com",
    "auth.openai.com",
    "platform.openai.com",
    "cdn.openai.com",
    "images.openai.com",
]


def hosts_path() -> Path:
    if sys.platform.startswith("win"):
        root = os.environ.get("SystemRoot", r"C:\Windows")
        return Path(root) / "System32" / "drivers" / "etc" / "hosts"
    return Path("/etc/hosts")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate():
    """Re-launch this process as admin (Windows)."""
    if is_admin():
        return True
    try:
        params = " ".join([f'"{s}"' for s in sys.argv])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, None, 1
        )
        return True
    except Exception:
        return False


def _read_hosts() -> str:
    p = hosts_path()
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _write_hosts(content: str) -> bool:
    p = hosts_path()
    try:
        p.write_text(content, encoding="utf-8")
        return True
    except PermissionError:
        return False
    except Exception:
        return False


def _strip_guard_block(text: str) -> str:
    """Remove any existing GPT-IP-GUARD block."""
    if MARK_BEGIN not in text:
        return text
    out_lines = []
    skip = False
    for line in text.splitlines(keepends=True):
        if line.strip() == MARK_BEGIN:
            skip = True
            continue
        if line.strip() == MARK_END:
            skip = False
            continue
        if not skip:
            out_lines.append(line)
    return "".join(out_lines)


def _build_block() -> str:
    lines = [MARK_BEGIN]
    for h in BLOCK_HOSTS:
        lines.append(f"127.0.0.1 {h}")
        lines.append(f"::1 {h}")
    lines.append(MARK_END)
    return "\n".join(lines) + "\n"


def apply_block() -> tuple[bool, str]:
    """Insert hosts block. Returns (ok, message)."""
    if not is_admin():
        return False, "需要管理员权限才能修改 hosts"
    text = _read_hosts()
    text = _strip_guard_block(text)
    if not text.endswith("\n"):
        text += "\n"
    text += _build_block()
    ok = _write_hosts(text)
    if ok:
        flush_dns()
        return True, "已通过 hosts 拦截 chatgpt.com / openai.com"
    return False, "hosts 写入失败"


def remove_block() -> tuple[bool, str]:
    """Remove hosts block."""
    if not is_admin():
        return False, "需要管理员权限才能修改 hosts"
    text = _read_hosts()
    new_text = _strip_guard_block(text)
    if new_text == text:
        return True, "hosts 中无拦截条目"
    ok = _write_hosts(new_text)
    if ok:
        flush_dns()
        return True, "已解除网站拦截"
    return False, "hosts 写入失败"


def is_blocked() -> bool:
    text = _read_hosts()
    return MARK_BEGIN in text


def flush_dns() -> None:
    try:
        if sys.platform.startswith("win"):
            subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except Exception:
        pass


if __name__ == "__main__":
    print("admin:", is_admin())
    print("blocked:", is_blocked())
