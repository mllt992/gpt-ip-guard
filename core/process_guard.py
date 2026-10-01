"""Detect & force-kill ChatGPT client when exit IP is not US."""
from __future__ import annotations

import os
import subprocess
import time
from typing import Callable, Optional

import psutil

# Common ChatGPT desktop process names on Windows
CHATGPT_PROCESS_NAMES = {
    "chatgpt.exe",
    "chatgpt",
    "openai chatgpt.exe",
}

# Common install paths (best-effort)
CANDIDATE_CLIENT_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\ChatGPT\ChatGPT.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\ChatGPT\ChatGPT.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\chatgpt\ChatGPT.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\ChatGPT\ChatGPT.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\OpenAI\ChatGPT\ChatGPT.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\ChatGPT\ChatGPT.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\ChatGPT\ChatGPT.exe"),
    os.path.expandvars(r"%USERPROFILE%\scoop\apps\chatgpt\current\ChatGPT.exe"),
    os.path.expandvars(r"%USERPROFILE%\AppData\Local\Packages\OpenAI.ChatGPT-Desktop_k5tx3h2x97k2t\LocalCache\ChatGPT.exe"),
]


def _reg_uninstall_paths() -> list[str]:
    """Find ChatGPT exe via registry uninstall entries + App Paths."""
    found = []
    try:
        import winreg
    except Exception:
        return found

    roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, sub in roots:
        try:
            k = winreg.OpenKey(hive, sub)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    sk = winreg.OpenKey(k, name)
                except OSError:
                    continue
                try:
                    try:
                        disp, _ = winreg.QueryValueEx(sk, "DisplayName")
                    except OSError:
                        disp = ""
                    loc = ""
                    try:
                        loc, _ = winreg.QueryValueEx(sk, "InstallLocation")
                    except OSError:
                        pass
                    icon = ""
                    try:
                        icon, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                    except OSError:
                        pass
                    blob = f"{disp} {loc} {icon}".lower()
                    if "chatgpt" in blob or "openai" in blob:
                        for p in (loc, icon.split(",")[0] if icon else ""):
                            p = (p or "").strip().strip('"')
                            if p and os.path.isfile(p) and p.lower().endswith(".exe"):
                                found.append(p)
                            elif p and os.path.isdir(p):
                                cand = os.path.join(p, "ChatGPT.exe")
                                if os.path.isfile(cand):
                                    found.append(cand)
                finally:
                    try:
                        winreg.CloseKey(sk)
                    except Exception:
                        pass
        finally:
            try:
                winreg.CloseKey(k)
            except Exception:
                pass

    # App Paths
    try:
        k = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\ChatGPT.exe",
        )
        try:
            val, _ = winreg.QueryValueEx(k, "")
            if val and os.path.isfile(val):
                found.append(val)
        finally:
            winreg.CloseKey(k)
    except OSError:
        pass

    return found


def _search_dirs_for_exe() -> list[str]:
    """Shallow search a few roots for ChatGPT.exe."""
    roots = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%LOCALAPPDATA%"),
        os.path.expandvars(r"%PROGRAMFILES%"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu"),
    ]
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for entry in os.listdir(root):
                if "chatgpt" not in entry.lower() and "openai" not in entry.lower():
                    continue
                p = os.path.join(root, entry)
                if os.path.isfile(p) and entry.lower() == "chatgpt.exe":
                    found.append(p)
                elif os.path.isdir(p):
                    for sub in os.listdir(p):
                        if sub.lower() == "chatgpt.exe":
                            found.append(os.path.join(p, sub))
                        # one more level
                        sp = os.path.join(p, sub)
                        if os.path.isdir(sp):
                            try:
                                for s2 in os.listdir(sp):
                                    if s2.lower() == "chatgpt.exe":
                                        found.append(os.path.join(sp, s2))
                            except OSError:
                                pass
        except OSError:
            continue
    return found


def find_chatgpt_exe() -> str:
    """Return best path to ChatGPT.exe or empty string."""
    seen = []

    def add(p: str):
        if p and p not in seen:
            seen.append(p)

    # 1) if running, use its exe
    try:
        for proc in find_chatgpt_processes():
            try:
                exe = proc.exe()
                if exe and os.path.isfile(exe):
                    add(exe)
                    break
            except Exception:
                pass
    except Exception:
        pass

    # 2) known paths
    for p in CANDIDATE_CLIENT_PATHS:
        if os.path.isfile(p):
            add(p)

    # 3) registry
    for p in _reg_uninstall_paths():
        add(p)

    # 4) shallow dir search
    for p in _search_dirs_for_exe():
        add(p)

    # 5) where.exe
    try:
        r = subprocess.run(
            ["where", "ChatGPT.exe"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0:
            for line in r.stdout.strip().splitlines():
                if os.path.isfile(line.strip()):
                    add(line.strip())
    except Exception:
        pass

    return seen[0] if seen else ""


def find_chatgpt_processes() -> list:
    found = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if name in CHATGPT_PROCESS_NAMES or "chatgpt" in name:
                found.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def kill_chatgpt() -> tuple[int, str]:
    """Force kill all ChatGPT processes. Returns (count, message)."""
    procs = find_chatgpt_processes()
    if not procs:
        return 0, "未检测到 ChatGPT 进程"
    killed = 0
    for p in procs:
        try:
            p.kill()
            killed += 1
        except Exception:
            # fallback to taskkill
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/F"],
                    capture_output=True,
                    timeout=6,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                killed += 1
            except Exception:
                pass
    return killed, f"已强制结束 {killed} 个 ChatGPT 进程"


def _run_start(cmd: str) -> bool:
    try:
        subprocess.Popen(
            cmd,
            shell=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True
    except Exception:
        return False


def launch_client() -> tuple[bool, str]:
    """Start ChatGPT desktop client (store / installed / protocol)."""
    # 1) direct exe
    exe = find_chatgpt_exe()
    if exe:
        try:
            subprocess.Popen([exe], shell=False)
            return True, f"已启动客户端: {exe}"
        except Exception as e:
            # try shell execute
            try:
                os.startfile(exe)  # type: ignore[attr-defined]
                return True, f"已启动客户端: {exe}"
            except Exception:
                return False, f"找到程序但启动失败: {e}"

    # 2) Start-menu .lnk
    for base in (
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"),
        os.path.expandvars(r"%USERPROFILE%\Desktop"),
    ):
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                if "chatgpt" in entry.lower() and entry.lower().endswith((".lnk", ".exe")):
                    p = os.path.join(base, entry)
                    if _run_start(f'start "" "{p}"') or os.path.isfile(p):
                        try:
                            os.startfile(p)  # type: ignore[attr-defined]
                            return True, f"已启动: {entry}"
                        except Exception:
                            if _run_start(f'start "" "{p}"'):
                                return True, f"已启动: {entry}"
        except OSError:
            continue

    # 3) URI / AUMID / store protocol
    attempts = [
        'start "" "chatgpt:"',
        'start "" shell:AppsFolder\\OpenAI.ChatGPT-Desktop_k5tx3h2x97k2t!ChatGPT',
        'start "" shell:AppsFolder\\ChatGPT.ChatGPT_1!ChatGPT',
        'powershell -c "start chatgpt:"',
    ]
    for cmd in attempts:
        if _run_start(cmd):
            return True, f"已尝试系统应用启动: {cmd[-40:]}"

    return False, (
        "未找到 ChatGPT 客户端。\n"
        "请确认已安装桌面版 ChatGPT，或手动安装后重试。"
    )


def launch_web(url: str = "https://chatgpt.com") -> tuple[bool, str]:
    import webbrowser

    try:
        webbrowser.open(url)
        return True, f"已打开 {url}"
    except Exception as e:
        return False, f"打开网页失败: {e}"


class GuardLoop:
    """Background loop: if enabled and IP not US and ChatGPT running → kill."""

    def __init__(
        self,
        is_us_provider: Callable[[], bool],
        on_kill: Optional[Callable[[str], None]] = None,
        interval: float = 5.0,
    ):
        self.is_us_provider = is_us_provider
        self.on_kill = on_kill
        self.interval = interval
        self.enabled = False
        self._running = False
        self._thread = None

    def start(self):
        import threading

        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                if self.enabled:
                    procs = find_chatgpt_processes()
                    if procs:
                        try:
                            is_us = bool(self.is_us_provider())
                        except Exception:
                            is_us = False
                        if not is_us:
                            n, msg = kill_chatgpt()
                            if self.on_kill:
                                self.on_kill(msg)
            except Exception:
                pass
            time.sleep(self.interval)
