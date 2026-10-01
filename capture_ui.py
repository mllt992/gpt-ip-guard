"""Capture clean window screenshots via PrintWindow (z-order independent)."""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "screenshots"
OUT.mkdir(exist_ok=True)

subprocess.run(["taskkill", "/F", "/IM", "GPT-IP-Guard.exe"], capture_output=True)
time.sleep(0.4)
proc = subprocess.Popen([sys.executable, "main.py"], cwd=str(ROOT))
time.sleep(5)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
hwnd = user32.FindWindowW(None, "GPT IP Guard")
print("hwnd", hwnd)
if not hwnd:
    sys.exit(1)

user32.SetForegroundWindow(hwnd)
time.sleep(0.4)


def print_window(hwnd, path: Path):
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    # include border
    wr = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    W = wr.right - wr.left
    H = wr.bottom - wr.top

    hdc = user32.GetDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, W, H)
    gdi32.SelectObject(memdc, bmp)
    # PW_RENDERFULLCONTENT = 2
    user32.PrintWindow(hwnd, memdc, 3)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = W
    bi.biHeight = -H  # top-down
    bi.biPlanes = 1
    bi.biBitCount = 32
    bi.biCompression = 0

    buf = ctypes.create_string_buffer(W * H * 4)
    gdi32.GetDIBits(memdc, bmp, 0, H, buf, ctypes.byref(bi), 0)

    from PIL import Image
    img = Image.frombuffer("RGBA", (W, H), buf, "raw", "BGRA", 0, 1)
    # drop alpha
    img = img.convert("RGB")
    img.save(path)
    print("saved", path, img.size)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)


print_window(hwnd, OUT / "status.png")

# click usage tab
rect = wintypes.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
cx, cy = rect.left + 130, rect.top + 82
user32.SetCursorPos(cx, cy)
user32.mouse_event(2, 0, 0, 0, 0)
user32.mouse_event(4, 0, 0, 0, 0)
time.sleep(1.0)
print_window(hwnd, OUT / "usage.png")

proc.terminate()
print("done")
