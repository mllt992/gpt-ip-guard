# -*- coding: utf-8 -*-
"""Build a single portable EXE (no Python needed on target PC)."""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
EXE_NAME = "GPT-IP-Guard"


def main():
    for d in (DIST, BUILD):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    # onefile + windowed: single .exe, no console, Python runtime bundled
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        f"--name={EXE_NAME}",
        "--icon", str(ROOT / "assets_icon.ico"),
        "--paths", str(ROOT),
        "--hidden-import", "psutil",
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--hidden-import", "charset_normalizer",
        "--hidden-import", "idna",
        "--hidden-import", "certifi",
        "--hidden-import", "pystray",
        "--hidden-import", "pystray._win32",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFont",
        # tkinter is stdlib; core package is local
        str(ROOT / "main.py"),
    ]

    print("Building portable EXE...")
    subprocess.check_call(cmd, cwd=str(ROOT))

    out = DIST / f"{EXE_NAME}.exe"
    if not out.exists():
        print("BUILD FAILED")
        sys.exit(1)

    size_mb = out.stat().st_size / 1024 / 1024
    print("\n" + "=" * 50)
    print(f"OK: {out}")
    print(f"Size: {size_mb:.1f} MB")
    print("发给别人的只有这一个文件，双击即可，不需要装 Python")
    print("=" * 50)

    # also drop a shortcut hint next to it
    readme = DIST / "使用说明.txt"
    readme.write_text(
        "GPT IP Guard 使用说明\n"
        "====================\n\n"
        "1. 只需要本文件夹里的 GPT-IP-Guard.exe 这一个文件\n"
        "2. 把它发给对方，对方双击运行即可，不需要安装 Python\n"
        "3. 若 Windows 提示「已保护你的电脑」：点「更多信息」→「仍要运行」\n"
        "4. 首次启动建议右键「以管理员身份运行」，否则无法拦截网站（hosts）\n"
        "5. 打开「强制守护」后，非美国出口会自动强杀 ChatGPT 客户端\n",
        encoding="utf-8",
    )
    print(f"Also wrote: {readme}")


if __name__ == "__main__":
    main()
