"""IP detection — simple, fast, hard-timeout. No thread pool complexity."""
from __future__ import annotations

import json
import re
import socket
import time
import urllib.request
from dataclasses import dataclass, asdict

TIMEOUT = 4
UA = {"User-Agent": "GPT-IP-Guard/1.2"}


@dataclass
class IPInfo:
    domestic_ip: str = ""
    foreign_ip: str = ""
    current_ip: str = ""
    domestic_meta: str = ""
    foreign_meta: str = ""
    current_meta: str = ""
    country: str = ""
    country_code: str = ""
    is_us: bool = False
    checking: bool = False
    error: str = ""

    def to_dict(self):
        return asdict(self)


def _http_get(url: str, timeout: float = TIMEOUT) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore").strip()


def _valid_ip(ip: str) -> bool:
    if not ip:
        return False
    try:
        socket.inet_aton(ip)
        return True
    except OSError:
        return False


def local_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _first_ok(fns, kind_label: str) -> tuple[str, str]:
    """Return first successful (ip, meta) from a list of zero-arg callables."""
    for fn in fns:
        try:
            ip, meta = fn()
            if _valid_ip(ip):
                return ip, meta or kind_label
        except Exception:
            continue
    return "", f"{kind_label}查询失败"


def _src_3322():
    ip = _http_get("https://ip.3322.net").split()[0].strip()
    return ip, "国内"


def _src_ipify():
    ip = _http_get("https://api.ipify.org").splitlines()[0].strip()
    return ip, "海外"


def _src_ipinfo():
    ip = _http_get("https://ipinfo.io/ip").splitlines()[0].strip()
    return ip, "海外"


def _src_ifconfig():
    ip = _http_get("https://ifconfig.me/ip").splitlines()[0].strip()
    return ip, "海外"


def _src_taobao():
    raw = _http_get("https://ip.taobao.com/service/getIpInfo.php?ip=myip")
    data = json.loads(raw)
    ip = (data.get("data") or {}).get("ip", "")
    return ip, "国内"


def geo_lookup(ip: str) -> tuple[str, str]:
    if not ip:
        return "", ""
    try:
        raw = _http_get(f"http://ip-api.com/json/{ip}?fields=status,country,countryCode", timeout=4)
        data = json.loads(raw)
        return data.get("country", ""), data.get("countryCode", "")
    except Exception:
        pass
    try:
        raw = _http_get(f"https://ipinfo.io/{ip}/json", timeout=4)
        data = json.loads(raw)
        return data.get("country", ""), data.get("country", "")
    except Exception:
        return "", ""


def collect() -> IPInfo:
    info = IPInfo(checking=False)
    info.current_ip = local_lan_ip()
    info.current_meta = "本机局域网"

    # sequential first-success (each call already has timeout)
    d_ip, d_meta = _first_ok([_src_3322, _src_taobao], "国内")
    info.domestic_ip = d_ip
    info.domestic_meta = d_meta

    f_ip, f_meta = _first_ok([_src_ipify, _src_ipinfo, _src_ifconfig], "海外")
    info.foreign_ip = f_ip
    info.foreign_meta = f_meta

    current_exit = f_ip or d_ip
    if not current_exit:
        info.error = "无法获取出口 IP，请检查网络"
        return info

    country, cc = geo_lookup(current_exit)
    info.country = country or ""
    info.country_code = cc or ""
    info.is_us = (cc or "").upper() == "US" or country == "美国" or "united states" in (country or "").lower()
    if country:
        info.foreign_meta = f"{info.foreign_meta} · {country}"
    info.current_ip = current_exit
    info.current_meta = f"生效出口 · {country or '未知'} · 本机 {local_lan_ip()}"
    return info


if __name__ == "__main__":
    t = time.time()
    print(json.dumps(collect().to_dict(), ensure_ascii=False, indent=2))
    print("elapsed", round(time.time() - t, 2))
