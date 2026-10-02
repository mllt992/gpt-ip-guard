"""GPT IP Guard — compact light UI + usage stats (portable)."""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog

BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _log_path() -> Path:
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent / "GPT-IP-Guard.log"
    except Exception:
        pass
    return Path.cwd() / "GPT-IP-Guard.log"


LOG_PATH = _log_path()


def flog(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


flog("=== app start ===")

from core import ip_checker, process_guard, blocker, usage, importer  # noqa: E402

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except Exception as e:
    HAS_TRAY = False
    flog(f"tray unavailable: {e}")

APP = "GPT IP Guard"
AUTOSTART_NAME = "GPTIPGuard"

BG = "#F1F5F9"
CARD = "#FFFFFF"
INK = "#0F172A"
DIM = "#64748B"
LINE = "#E2E8F0"
SAFE = "#16A34A"
SAFE_BG = "#ECFDF3"
DANGER = "#DC2626"
DANGER_BG = "#FEF2F2"
ACCENT = "#2563EB"
ACCENT_BG = "#EFF6FF"
WARN = "#D97706"
WARN_BG = "#FFFBEB"
DISABLED_BG = "#E2E8F0"
DISABLED_FG = "#94A3B8"
PURPLE = "#7C3AED"
ORANGE = "#EA580C"

FONT = ("Segoe UI", 9)
FONT_S = ("Segoe UI", 8)
FONT_B = ("Segoe UI", 9, "bold")
FONT_T = ("Segoe UI", 12, "bold")
FONT_IP = ("Consolas", 10, "bold")
FONT_NUM = ("Segoe UI", 14, "bold")


# ---------- single instance ----------
MUTEX_NAME = "Global\\GPTIPGuard_SingleInstance"
_mutex = None


def _ensure_single_instance() -> bool:
    global _mutex
    try:
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        _mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "GPT IP Guard")
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
            return False
        return True
    except Exception as e:
        flog(f"mutex err {e}")
        return True


def exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def is_autostart() -> bool:
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(k, AUTOSTART_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(k)
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    try:
        import winreg
        k = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        if enabled:
            path = exe_path()
            if not path.startswith('"'):
                path = f'"{path}"'
            winreg.SetValueEx(k, AUTOSTART_NAME, 0, winreg.REG_SZ, path)
        else:
            try:
                winreg.DeleteValue(k, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(k)
        return True
    except Exception as e:
        flog(f"autostart err {e}")
        return False


def make_icon() -> "Image.Image":
    s = 64
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s // 5, fill=(37, 99, 235, 255))
    top, bot, left, right = int(s * 0.16), int(s * 0.86), int(s * 0.22), int(s * 0.78)
    midx = s // 2
    d.polygon([
        (midx, top), (right, int(s * 0.28)), (right, int(s * 0.52)),
        (midx, bot), (left, int(s * 0.52)), (left, int(s * 0.28)),
    ], fill=(59, 130, 246, 255))
    d.polygon([
        (midx, int(s * 0.22)), (int(s * 0.70), int(s * 0.32)), (int(s * 0.70), int(s * 0.52)),
        (midx, int(s * 0.78)), (int(s * 0.30), int(s * 0.52)), (int(s * 0.30), int(s * 0.32)),
    ], fill=(96, 165, 250, 255))
    d.line([
        (int(s * 0.34), int(s * 0.50)), (int(s * 0.46), int(s * 0.62)), (int(s * 0.68), int(s * 0.34)),
    ], fill=(255, 255, 255, 255), width=max(4, s // 16), joint="curve")
    return img


def _fmt_n(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(int(n))


class App:
    def __init__(self, root: tk.Tk):
        flog("App.__init__")
        self.root = root
        self.root.title(APP)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        w, h = 400, 640
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        self.result_box = None
        self.detecting = False
        self.is_us = False
        self.guard_on = False
        self.block_on = True
        self._last_us = None
        self.tray = None
        self.full_ips = {"domestic": "", "foreign": "", "current": ""}
        self.mask_on = True
        self.range_days = 30  # 7 / 30 / 0(all)
        self.detect_interval = self._load_interval()  # seconds, default 300

        usage.init_db()
        # first-run: import real local Codex token usage
        def _boot_import():
            try:
                if usage.totals().get("count", 0) == 0:
                    if importer.ensure_imported():
                        self.root.after(0, lambda: self._append("已自动同步本机真实 token 用量", "ok"))
                        self.root.after(50, self._refresh_usage_ui)
            except Exception as e:
                flog(f"boot import {e}")

        threading.Thread(target=_boot_import, daemon=True).start()
        self._build()
        flog("UI built")

        self.root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self._init_tray()
        self.root.after(150, self._poll_result)
        self.root.after(300, self._start_detect)
        self._workers()
        self.root.after(400, self._refresh_usage_ui)
        self.root.after(900, self._refresh_usage_ui)  # redraw chart after layout
        self._append(f"就绪 · 自动检测 {self.detect_interval // 60} 分钟一轮", "info")

    def _config_path(self) -> Path:
        try:
            if getattr(sys, "frozen", False):
                return Path(sys.executable).parent / "gpt-ip-guard-config.json"
        except Exception:
            pass
        return Path(__file__).resolve().parent / "gpt-ip-guard-config.json"

    def _load_interval(self) -> int:
        default = 300
        try:
            data = json.loads(self._config_path().read_text(encoding="utf-8"))
            sec = int(data.get("detect_interval_sec", default))
            return min(max(sec, 60), 3600)
        except Exception:
            return default

    def _save_interval(self, sec: int):
        try:
            p = self._config_path()
            data = {}
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
            data["detect_interval_sec"] = int(sec)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            flog(f"save interval {e}")

    # ---------- tray ----------
    def _init_tray(self):
        if not HAS_TRAY:
            return

        def on_show(icon=None, item=None):
            self.root.after(0, self._show_window)

        def on_autostart(icon=None, item=None):
            cur = is_autostart()
            ok = set_autostart(not cur)
            self.root.after(0, lambda: self._append(
                "已开启开机自启" if (not cur and ok) else ("已关闭开机自启" if ok else "设置开机自启失败"),
                "ok" if ok else "error",
            ))
            try:
                icon.update_menu()
            except Exception:
                pass

        def on_exit(icon=None, item=None):
            self.root.after(0, self._real_quit)

        menu = pystray.Menu(
            pystray.MenuItem("显示主界面", on_show, default=True),
            pystray.MenuItem(lambda item: "✓ 开机自启" if is_autostart() else "开机自启", on_autostart),
            pystray.MenuItem("退出", on_exit),
        )
        try:
            self.tray = pystray.Icon("GPTIPGuard", make_icon(), APP, menu)
            threading.Thread(target=self.tray.run, daemon=True).start()
            flog("tray started")
        except Exception as e:
            flog(f"tray start err {e}")

    def _hide_to_tray(self):
        self.root.withdraw()
        self._append("已最小化到托盘", "info")

    def _show_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception as e:
            flog(f"show err {e}")

    def _real_quit(self):
        flog("quit")
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------- UI ----------
    def _build(self):
        # header
        hd = tk.Frame(self.root, bg=BG)
        hd.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(hd, text="GPT IP Guard", font=FONT_T, bg=BG, fg=INK).pack(side="left")
        right = tk.Frame(hd, bg=BG)
        right.pack(side="right")
        tk.Button(
            right, text="刷新", command=self._start_detect, font=FONT_S,
            bg=CARD, fg=ACCENT, relief="flat", padx=8, pady=2, cursor="hand2",
            highlightbackground=LINE, highlightthickness=1,
        ).pack(side="left", padx=(0, 4))
        # interval: 1/3/5/10 min
        tk.Label(right, text="间隔", font=FONT_S, bg=BG, fg=DIM).pack(side="left", padx=(2, 2))
        self.interval_var = tk.StringVar(value=f"{self.detect_interval // 60}")
        combo = tk.OptionMenu(right, self.interval_var, "1", "3", "5", "10", command=self._on_interval)
        combo.configure(font=FONT_S, width=2, highlightthickness=0, relief="flat", bg=CARD)
        combo.pack(side="left", padx=(0, 6))
        tk.Label(right, text="分", font=FONT_S, bg=BG, fg=DIM).pack(side="left", padx=(0, 6))
        self.auto_var = tk.BooleanVar(value=is_autostart())
        tk.Checkbutton(
            right, text="开机自启", variable=self.auto_var, font=FONT_S, bg=BG,
            activebackground=BG, highlightthickness=0, command=self._toggle_autostart,
        ).pack(side="left")

        # modern pill tabs
        tabbar = tk.Frame(self.root, bg="#E2E8F0", highlightthickness=0)
        tabbar.pack(fill="x", padx=10, pady=(6, 2))
        pill = tk.Frame(tabbar, bg="#E2E8F0")
        pill.pack(padx=4, pady=4)
        self.tab_buttons = {}
        self.tab_frames = {}

        def switch_tab(name):
            for k, btn in self.tab_buttons.items():
                btn.configure(bg=CARD if k == name else "#E2E8F0", fg=INK if k == name else DIM)
            for k, fr in self.tab_frames.items():
                if k == name:
                    fr.pack(fill="both", expand=True)
                else:
                    fr.pack_forget()
            if name == "usage":
                self.root.after(50, self._refresh_usage_ui)

        for key, label in [("status", "状态"), ("usage", "用量")]:
            btn = tk.Label(
                pill, text=f"  {label}  ", font=FONT_B, bg="#E2E8F0", fg=DIM,
                cursor="hand2", padx=16, pady=6,
            )
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda e, k=key: switch_tab(k))
            self.tab_buttons[key] = btn

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=(2, 4))
        self.tab_status = tk.Frame(body, bg=BG)
        self.tab_usage = tk.Frame(body, bg=BG)
        self.tab_frames = {"status": self.tab_status, "usage": self.tab_usage}
        self._build_status_tab(self.tab_status)
        self._build_usage_tab(self.tab_usage)
        start_tab = "status"
        if len(sys.argv) > 1 and sys.argv[1] in ("status", "usage"):
            start_tab = sys.argv[1]
        switch_tab(start_tab)

    def _build_status_tab(self, parent):
        # status strip
        self.strip = tk.Frame(parent, bg=ACCENT_BG, highlightbackground=LINE, highlightthickness=1)
        self.strip.pack(fill="x", pady=(8, 4))
        sf = tk.Frame(self.strip, bg=ACCENT_BG)
        sf.pack(fill="x", padx=10, pady=8)
        self.dot = tk.Label(sf, text="●", font=("Segoe UI", 11), bg=ACCENT_BG, fg=ACCENT)
        self.dot.pack(side="left")
        mid = tk.Frame(sf, bg=ACCENT_BG)
        mid.pack(side="left", fill="x", expand=True, padx=8)
        self.title = tk.Label(mid, text="正在检测出口…", font=FONT_B, bg=ACCENT_BG, fg=INK, anchor="w")
        self.title.pack(fill="x")
        self.sub = tk.Label(mid, text="请稍候", font=FONT_S, bg=ACCENT_BG, fg=DIM, anchor="w")
        self.sub.pack(fill="x")
        self.pill = tk.Label(sf, text="…", font=FONT_S, bg=CARD, fg=DIM, padx=8, pady=2)
        self.pill.pack(side="right")

        # IPs
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="x", pady=4)
        tk.Label(box, text="点击 IP 显示/隐藏", font=("Segoe UI", 7), bg=CARD, fg=DIM, anchor="w").pack(fill="x", padx=10, pady=(6, 0))
        self.rows = {}
        for i, (key, name) in enumerate([("domestic", "国内出口"), ("foreign", "海外出口"), ("current", "当前出口")]):
            if i:
                tk.Frame(box, bg=LINE, height=1).pack(fill="x", padx=10)
            r = tk.Frame(box, bg=CARD)
            r.pack(fill="x", padx=10, pady=5)
            tk.Label(r, text=name, font=FONT_S, bg=CARD, fg=DIM, width=7, anchor="w").pack(side="left")
            val = tk.Label(r, text="--", font=FONT_IP, bg=CARD, fg=INK, anchor="e", cursor="hand2")
            val.pack(side="right")
            val.bind("<Button-1>", lambda e, k=key: self._toggle_ip(k))
            self.rows[key] = val

        # country + launch row
        info = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        info.pack(fill="x", pady=4)
        r = tk.Frame(info, bg=CARD)
        r.pack(fill="x", padx=10, pady=5)
        tk.Label(r, text="出口地区", font=FONT_S, bg=CARD, fg=DIM).pack(side="left")
        self.country = tk.Label(r, text="--", font=FONT_B, bg=CARD, fg=INK)
        self.country.pack(side="right")
        r = tk.Frame(info, bg=CARD)
        r.pack(fill="x", padx=10, pady=(0, 5))
        tk.Label(r, text="美国出口", font=FONT_S, bg=CARD, fg=DIM).pack(side="left")
        self.us = tk.Label(r, text="--", font=FONT_B, bg=CARD, fg=DIM)
        self.us.pack(side="right")

        self.btn_client = tk.Button(
            parent, text="启动客户端", command=self._launch_client, font=FONT_B,
            bg=DISABLED_BG, fg=DISABLED_FG, relief="flat", pady=8, cursor="hand2",
            state="disabled", disabledforeground=DISABLED_FG,
        )
        self.btn_client.pack(fill="x", pady=(6, 3))
        self.btn_web = tk.Button(
            parent, text="启动网页 chatgpt.com", command=self._launch_web, font=FONT,
            bg=DISABLED_BG, fg=DISABLED_FG, relief="flat", pady=7, cursor="hand2",
            state="disabled", disabledforeground=DISABLED_FG,
            highlightbackground=LINE, highlightthickness=1,
        )
        self.btn_web.pack(fill="x", pady=3)

        self._switch_row(parent, "强制守护", "非美国出口自动结束 ChatGPT", "guard", False)
        self._switch_row(parent, "网站拦截", "非美国时拦截 chatgpt / openai", "block", True)

        # log — full height, readable
        lg = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        lg.pack(fill="both", expand=True, pady=(6, 8))
        top = tk.Frame(lg, bg=CARD)
        top.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(top, text="运行日志", font=FONT_B, bg=CARD, fg=INK).pack(side="left")
        tk.Button(
            top, text="清空", font=FONT_S, command=self._clear_log, bg=CARD, fg=DIM,
            relief="flat", padx=6, pady=1, cursor="hand2", highlightbackground=LINE, highlightthickness=1,
        ).pack(side="right")
        self.log = tk.Text(
            lg, height=8, bg="#F8FAFC", fg=INK, relief="flat", font=("Consolas", 9),
            wrap="word", state="disabled", highlightbackground=LINE, highlightthickness=1,
            padx=8, pady=6, spacing1=1, spacing3=1,
        )
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.log.tag_configure("info", foreground="#0369A1")
        self.log.tag_configure("ok", foreground=SAFE)
        self.log.tag_configure("warn", foreground="#B45309")
        self.log.tag_configure("error", foreground=DANGER)

    def _build_usage_tab(self, parent):
        # range filter
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(8, 4))
        tk.Label(bar, text="时间范围", font=FONT_S, bg=BG, fg=DIM).pack(side="left")
        self.range_var = tk.StringVar(value="30")
        for label, val in [("7天", "7"), ("30天", "30"), ("全部", "0")]:
            tk.Radiobutton(
                bar, text=label, variable=self.range_var, value=val, font=FONT_S, bg=BG,
                activebackground=BG, command=self._on_range,
            ).pack(side="left", padx=4)
        tk.Button(
            bar, text="记录用量", font=FONT_S, command=self._add_usage,
            bg=ACCENT, fg="white", relief="flat", padx=8, pady=2, cursor="hand2",
        ).pack(side="right")
        tk.Button(
            bar, text="导入本机数据", font=FONT_S, command=self._import_local,
            bg=CARD, fg=INK, relief="flat", padx=8, pady=2, cursor="hand2",
            highlightbackground=LINE, highlightthickness=1,
        ).pack(side="right", padx=4)

        # KPI cards
        kpi = tk.Frame(parent, bg=BG)
        kpi.pack(fill="x", pady=4)
        self.kpi_labels = {}
        for key, title, color in [
            ("input", "输入", ACCENT),
            ("output", "输出", PURPLE),
            ("cache", "缓存(含)", ORANGE),
            ("total", "合计", SAFE),
        ]:
            card = tk.Frame(kpi, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            card.pack(side="left", expand=True, fill="both", padx=2)
            tk.Label(card, text=title, font=FONT_S, bg=CARD, fg=DIM).pack(padx=2, pady=(6, 0))
            lb = tk.Label(card, text="0", font=("Segoe UI", 11, "bold"), bg=CARD, fg=color)
            lb.pack(padx=2, pady=(0, 6))
            self.kpi_labels[key] = lb

        # chart
        chart_box = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        chart_box.pack(fill="both", expand=True, pady=4)
        tk.Label(chart_box, text="Token 消耗趋势", font=FONT_B, bg=CARD, fg=INK, anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        # legend
        lgd = tk.Frame(chart_box, bg=CARD)
        lgd.pack(fill="x", padx=10)
        for name, color in [("输入", ACCENT), ("输出", PURPLE), ("缓存", ORANGE)]:
            tk.Label(lgd, text=f"● {name}", font=FONT_S, bg=CARD, fg=color).pack(side="left", padx=(0, 10))
        self.chart = tk.Canvas(chart_box, bg="#F8FAFC", highlightthickness=1, highlightbackground=LINE, height=180)
        self.chart.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        # bottom actions
        bot = tk.Frame(parent, bg=BG)
        bot.pack(fill="x", pady=(2, 8))
        tk.Button(
            bot, text="刷新统计", font=FONT_S, command=self._refresh_usage_manual,
            bg=CARD, fg=INK, relief="flat", padx=8, pady=3, cursor="hand2",
            highlightbackground=LINE, highlightthickness=1,
        ).pack(side="left")
        tk.Button(
            bot, text="清空数据", font=FONT_S, command=self._clear_usage,
            bg=CARD, fg=DANGER, relief="flat", padx=8, pady=3, cursor="hand2",
            highlightbackground=LINE, highlightthickness=1,
        ).pack(side="right")

    def _switch_row(self, parent, title, desc, kind, default):
        row = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        row.pack(fill="x", pady=3)
        left = tk.Frame(row, bg=CARD)
        left.pack(side="left", fill="x", expand=True, padx=10, pady=6)
        tk.Label(left, text=title, font=FONT_B, bg=CARD, fg=INK, anchor="w").pack(fill="x")
        tk.Label(left, text=desc, font=FONT_S, bg=CARD, fg=DIM, anchor="w").pack(fill="x")
        var = tk.BooleanVar(value=default)
        tk.Checkbutton(
            row, variable=var, bg=CARD, activebackground=CARD, highlightthickness=0,
            command=lambda k=kind, v=var: self._on_switch(k, v.get()),
        ).pack(side="right", padx=10)
        if kind == "guard":
            self.guard_var = var
        else:
            self.block_var = var

    # ---------- log / status ----------
    def _append(self, msg, level="info"):
        try:
            self.log.configure(state="normal")
            self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {msg}\n", level)
            self.log.see("end")
            self.log.configure(state="disabled")
        except Exception:
            pass
        flog(msg)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_status(self, kind, title, sub, pill):
        colors = {
            "safe": (SAFE_BG, SAFE),
            "danger": (DANGER_BG, DANGER),
            "warn": (WARN_BG, WARN),
            "info": (ACCENT_BG, ACCENT),
        }
        bg, fg = colors.get(kind, (ACCENT_BG, ACCENT))
        try:
            self.strip.configure(bg=bg)
            for w in self.strip.winfo_children():
                w.configure(bg=bg)
                for c in w.winfo_children():
                    c.configure(bg=bg)
            self.dot.configure(bg=bg, fg=fg)
            self.title.configure(bg=bg, text=title)
            self.sub.configure(bg=bg, text=sub)
            self.pill.configure(text=pill, fg=fg, bg=CARD)
        except Exception as e:
            flog(f"set_status err {e}")

    def _set_launch_enabled(self, enabled: bool):
        if enabled:
            self.btn_client.config(state="normal", bg=ACCENT, fg="white")
            self.btn_web.config(state="normal", bg=CARD, fg=ACCENT)
        else:
            self.btn_client.config(state="disabled", bg=DISABLED_BG, fg=DISABLED_FG)
            self.btn_web.config(state="disabled", bg=DISABLED_BG, fg=DISABLED_FG)

    def _mask_ip(self, ip: str) -> str:
        if not ip:
            return "--"
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.*.*.*"
        return (ip.split(":")[0] if ":" in ip else ip[:3]) + ":*:*"

    def _toggle_ip(self, key: str):
        self.mask_on = not self.mask_on
        self._refresh_ip_display()
        self._append("已显示完整 IP" if not self.mask_on else "已隐藏 IP 后三段", "info")

    def _refresh_ip_display(self):
        for key, val in self.rows.items():
            ip = self.full_ips.get(key) or ""
            val.config(text="--" if not ip else (self._mask_ip(ip) if self.mask_on else ip))

    def _render(self, d: dict):
        flog(f"render us={d.get('is_us')} err={d.get('error')} fip={d.get('foreign_ip')}")
        self.full_ips["domestic"] = d.get("domestic_ip") or ""
        self.full_ips["foreign"] = d.get("foreign_ip") or ""
        self.full_ips["current"] = d.get("current_ip") or ""
        self._refresh_ip_display()
        self.country.config(text=d.get("country") or "未知")
        is_us = bool(d.get("is_us"))
        self.is_us = is_us

        if d.get("error") and not is_us and not d.get("foreign_ip"):
            self.us.config(text="检测失败", fg=WARN)
            self._set_status("warn", "检测失败", str(d.get("error"))[:48], "错误")
            self._set_launch_enabled(False)
            return
        if is_us:
            self.us.config(text="✔ 可安全启动", fg=SAFE)
            self._set_status("safe", "海外出口为美国", f"{d.get('country') or 'US'} · 可启动 GPT", "安全")
            self._set_launch_enabled(True)
        else:
            self.us.config(text="✘ 已拦截", fg=DANGER)
            self._set_status("danger", "海外出口不是美国", f"{d.get('country') or '未知'} · 请换美国节点", "拦截")
            self._set_launch_enabled(False)

    # ---------- detect ----------
    def _start_detect(self):
        if self.detecting:
            return
        self.detecting = True
        self.result_box = None
        self._last_detect_ts = time.time()
        self._set_status("info", "正在检测出口…", "请稍候 1–6 秒", "…")

        def worker():
            t0 = time.time()
            try:
                info = ip_checker.collect()
                self.result_box = info.to_dict()
                flog(f"collect ok {time.time()-t0:.2f}s us={info.is_us}")
            except Exception as e:
                flog(f"collect EXC {e}")
                self.result_box = {"error": str(e), "is_us": False}

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(8000, self._watchdog)

    def _watchdog(self):
        if self.result_box is not None or not self.detecting:
            return
        self.detecting = False
        self._append("检测超时（8 秒）", "error")
        self._render({"error": "检测超时", "is_us": False})

    def _poll_result(self):
        try:
            if self.result_box is not None:
                data = self.result_box
                self.result_box = None
                self.detecting = False
                self._render(data)
                threading.Thread(target=self._apply_block, daemon=True).start()
                us = bool(data.get("is_us"))
                if self._last_us is not None and self._last_us != us:
                    self._append("出口已切换为美国" if us else "出口不是美国，开始拦截", "ok" if us else "warn")
                self._last_us = us
        except Exception as e:
            flog(f"poll err {e}")
        self.root.after(150, self._poll_result)

    # ---------- usage ----------
    def _refresh_usage_manual(self):
        """Manual refresh: re-sync from local logs then redraw."""
        self._append("正在刷新用量统计…", "info")

        def work():
            try:
                r = importer.sync_usage(True)
                msg = f"用量已刷新：{r['records']} 条响应"
            except Exception as e:
                msg = f"用量刷新失败: {e}"
            self.root.after(0, lambda: self._append(msg, "ok"))
            self.root.after(30, self._refresh_usage_ui)

        threading.Thread(target=work, daemon=True).start()

    def _on_range(self):
        self.range_days = int(self.range_var.get())
        self._refresh_usage_ui()

    def _refresh_usage_ui(self):
        days = self.range_days
        t = usage.totals(days if days > 0 else None)
        self.kpi_labels["input"].config(text=_fmt_n(t["input_tokens"]))
        self.kpi_labels["output"].config(text=_fmt_n(t["output_tokens"]))
        self.kpi_labels["cache"].config(text=_fmt_n(t["cache_tokens"]))
        self.kpi_labels["total"].config(text=_fmt_n(t["total_tokens"]))
        series = usage.daily_series(days if days > 0 else 9999)
        self._draw_chart(series)

    def _draw_chart(self, series: list):
        c = self.chart
        c.delete("all")
        w = int(c.winfo_width() or 360)
        h = int(c.winfo_height() or 180)
        if w < 50 or h < 50:
            return
        pad_l, pad_r, pad_t, pad_b = 36, 10, 12, 24
        pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
        if pw <= 0 or ph <= 0:
            return

        if not series:
            c.create_text(w // 2, h // 2, text="暂无数据，点击「记录用量」添加", fill=DIM, font=FONT)
            return

        keys = ["input_tokens", "output_tokens", "cache_tokens"]
        colors = [ACCENT, PURPLE, ORANGE]
        vmax = 1
        for s in series:
            for k in keys:
                vmax = max(vmax, s.get(k, 0))
        # nice max
        if vmax < 10:
            vmax = 10

        # grid
        for i in range(5):
            y = pad_t + ph * i / 4
            c.create_line(pad_l, y, w - pad_r, y, fill=LINE)
            val = vmax * (1 - i / 4)
            c.create_text(pad_l - 6, y, text=_fmt_n(int(val)), fill=DIM, font=("Segoe UI", 7), anchor="e")

        n = len(series)
        def x_at(i):
            return pad_l + (pw * (i / max(n - 1, 1)) if n > 1 else pw / 2)

        # x labels (sparse)
        step = max(1, n // 6)
        for i, s in enumerate(series):
            if i % step == 0 or i == n - 1:
                c.create_text(x_at(i), h - 10, text=s["date"][-5:], fill=DIM, font=("Segoe UI", 7), anchor="s")

        for key, color in zip(keys, colors):
            pts = []
            for i, s in enumerate(series):
                v = s.get(key, 0)
                y = pad_t + ph * (1 - v / vmax)
                pts.extend([x_at(i), y])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=2, smooth=True)
            for i, s in enumerate(series):
                v = s.get(key, 0)
                if v > 0:
                    y = pad_t + ph * (1 - v / vmax)
                    c.create_oval(x_at(i) - 3, y - 3, x_at(i) + 3, y + 3, fill=color, outline=color)

    def _import_local(self):
        self._append("正在同步本机 ChatGPT token 用量…", "info")

        def work():
            try:
                r = importer.sync_usage(True)
                msg = f"已同步 {r['records']} 条真实用量（按 response 去重）"
            except Exception as e:
                msg = f"同步失败: {e}"
            self.root.after(0, lambda: self._append(msg, "ok"))
            self.root.after(30, self._refresh_usage_ui)

        threading.Thread(target=work, daemon=True).start()

    def _add_usage(self):
        win = tk.Toplevel(self.root)
        win.title("记录 Token 用量")
        win.configure(bg=BG)
        win.geometry("320x260")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        fields = {}
        for i, (key, label, default) in enumerate([
            ("input", "输入 tokens", "1200"),
            ("output", "输出 tokens", "800"),
            ("cache", "缓存 tokens", "300"),
        ]):
            tk.Label(win, text=label, font=FONT, bg=BG, fg=INK).place(x=24, y=24 + i * 40)
            ent = tk.Entry(win, font=FONT, width=12)
            ent.insert(0, default)
            ent.place(x=160, y=22 + i * 40)
            fields[key] = ent

        tk.Label(win, text="备注（可选）", font=FONT, bg=BG, fg=INK).place(x=24, y=150)
        note = tk.Entry(win, font=FONT, width=18)
        note.place(x=160, y=148)

        def save():
            try:
                usage.add_record(
                    int(fields["input"].get() or 0),
                    int(fields["output"].get() or 0),
                    int(fields["cache"].get() or 0),
                    source="manual",
                    note=note.get().strip(),
                )
                self._append("已记录 Token 用量", "ok")
                self._refresh_usage_ui()
                win.destroy()
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}", parent=win)

        tk.Button(win, text="保存", command=save, bg=ACCENT, fg="white", font=FONT_B, relief="flat", padx=16, pady=4).place(x=110, y=195)
        tk.Button(win, text="取消", command=win.destroy, font=FONT, relief="flat", padx=12, pady=4).place(x=190, y=195)

    def _clear_usage(self):
        if messagebox.askyesno("确认", "确定清空全部用量数据？"):
            usage.clear_all()
            self._refresh_usage_ui()
            self._append("用量数据已清空", "warn")

    # ---------- actions ----------
    def _on_interval(self, value: str):
        try:
            minutes = int(value)
        except Exception:
            minutes = 5
        self.detect_interval = max(60, minutes * 60)
        self._save_interval(self.detect_interval)
        self._append(f"检测间隔已设为 {minutes} 分钟", "info")

    def _toggle_autostart(self):
        want = self.auto_var.get()
        ok = set_autostart(want)
        self._append(("已开启开机自启" if want else "已关闭开机自启") if ok else "设置开机自启失败", "ok" if ok else "error")
        if not ok:
            self.auto_var.set(is_autostart())

    def _on_switch(self, kind, value):
        if kind == "guard":
            self.guard_on = value
            self._append("强制守护已开启" if value else "强制守护已关闭", "warn" if value else "info")
            if value and not self.is_us and process_guard.find_chatgpt_processes():
                n, msg = process_guard.kill_chatgpt()
                self._append(msg, "error")
        else:
            self.block_on = value
            threading.Thread(target=self._apply_block, daemon=True).start()

    def _apply_block(self):
        try:
            if not self.block_on:
                ok, msg = blocker.remove_block()
                self.root.after(0, lambda: self._append(msg, "info" if ok else "error"))
            elif self.is_us:
                ok, msg = blocker.remove_block()
                self.root.after(0, lambda: self._append(msg, "ok" if ok else "error"))
            else:
                ok, msg = blocker.apply_block()
                self.root.after(0, lambda: self._append(msg, "warn" if ok else "error"))
        except Exception as e:
            flog(f"block err {e}")

    def _launch_client(self):
        if not self.is_us:
            self._append("非美国出口，禁止启动", "error")
            return

        def work():
            ok, msg = process_guard.launch_client()
            if ok:
                usage.add_record(source="client", note="launch client")
            self.root.after(0, lambda: self._append(msg, "ok" if ok else "error"))

        threading.Thread(target=work, daemon=True).start()

    def _launch_web(self):
        if not self.is_us:
            self._append("非美国出口，禁止打开网页", "error")
            return

        def work():
            ok, msg = process_guard.launch_web()
            if ok:
                usage.add_record(source="web", note="launch web")
            self.root.after(0, lambda: self._append(msg, "ok" if ok else "error"))

        threading.Thread(target=work, daemon=True).start()

    def _workers(self):
        def guard():
            while True:
                try:
                    if self.guard_on and not self.is_us and process_guard.find_chatgpt_processes():
                        n, msg = process_guard.kill_chatgpt()
                        flog(msg)
                except Exception:
                    pass
                time.sleep(5)

        def auto():
            while True:
                # wake often, fire when interval elapsed
                time.sleep(min(30, max(5, self.detect_interval)))
                self.root.after(0, self._maybe_auto_detect)

        threading.Thread(target=guard, daemon=True).start()
        threading.Thread(target=auto, daemon=True).start()
        self._last_detect_ts = time.time()

    def _maybe_auto_detect(self):
        if time.time() - getattr(self, "_last_detect_ts", 0) >= self.detect_interval - 1:
            self._start_detect()


def main():
    flog("main()")
    if not _ensure_single_instance():
        flog("exit: already running")
        sys.exit(0)
    try:
        root = tk.Tk()
        App(root)
        flog("mainloop")
        root.mainloop()
        flog("mainloop end")
    except Exception:
        err = traceback.format_exc()
        flog(err)
        try:
            messagebox.showerror(APP, f"启动失败:\n{err}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
