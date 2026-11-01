"""无控制台启动模型物理工具，并在 Edge／Chrome 应用窗口中打开。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

from . import server as SV

QUIET = 8
SILENT = 240
FIRST = 90
TITLE = "Retroport 模型物理工具"


def browser() -> str:
    roots = [os.environ.get(v, "") for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
        for root in roots:
            path = os.path.join(root, rel) if root else ""
            if path and os.path.isfile(path):
                return path
    return ""


def open_window(url: str, profile: str):
    exe = browser()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return None
    return subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                             "--no-default-browser-check", "--disable-background-mode", "--window-size=1180,900"],
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "api/meta", timeout=3) as response:
            return json.load(response).get("name") == SV.APP_NAME
    except Exception:
        return False


def running_app(url: str) -> dict:
    try:
        with urllib.request.urlopen(url + "api/status", timeout=5) as response:
            return json.load(response).get("app") or {}
    except Exception:
        return {}


def same_copy(other: dict, mine: dict) -> bool:
    return bool(other) and os.path.normcase(other.get("from", "")) == os.path.normcase(mine["from"]) and \
        other.get("code", 0) >= mine["code"] - 1


def take_over(url: str, wait: float = 30.0) -> str:
    try:
        request = urllib.request.Request(url + "api/quit", data=b"{}", method="POST",
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=5).close()
    except Exception as e:
        return str(e)
    end = time.time() + wait
    while time.time() < end:
        time.sleep(0.5)
        if not running(url):
            return ""
    return "旧实例没有停止"


def ask(text: str) -> bool:
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x4 | 0x20) == 6
    except Exception:
        return False


def should_end(wb: SV.Workbench, started: float, now: float, window_open: bool) -> bool:
    if wb.quitting and not wb.busy():
        return True
    if wb.busy() or window_open:
        return False
    hello, bye = wb.last_hello, wb.last_bye
    if not hello:
        return now - started > FIRST
    if bye >= hello:
        return now - bye > QUIET
    return now - hello > SILENT


def message(text: str) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)
    except Exception:
        pass


def main() -> int:
    settings = SV.Settings.load()
    data = settings.data_dir
    os.makedirs(data, exist_ok=True)
    log_path = os.path.join(data, "workbench.log")
    if os.path.isfile(log_path) and os.path.getsize(log_path) > 4 << 20:
        os.replace(log_path, log_path + ".old")
    log = open(log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None or getattr(sys, "frozen", False) or os.path.basename(sys.executable).lower() == "pythonw.exe":
        sys.stdout = sys.stderr = log
    port = SV.PORT
    url = f"http://127.0.0.1:{port}/"
    profile = os.path.join(data, "window")
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} {TITLE} 正在启动", flush=True)
    mine = SV.app_info()
    try:
        try:
            httpd, wb = SV.start_server(settings, port)
        except OSError:
            if not running(url):
                raise
            other = running_app(url)
            if same_copy(other, mine):
                open_window(url, profile)
                return 0
            who = f"{TITLE} {other.get('version', '')}" if other else "旧版模型物理工具"
            if not other or not ask(f"{who} 正在运行。\n\n停止旧实例并启动这个实例吗？"):
                open_window(url, profile)
                return 0
            why = take_over(url)
            if why:
                message(f"无法停止旧实例：{why}")
                return 1
            httpd, wb = SV.start_server(settings, port)
    except Exception as e:
        traceback.print_exc()
        message(f"工具无法启动：\n\n{type(e).__name__}: {e}\n\n日志：{log_path}")
        return 1
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    print(f"监听 {url}", flush=True)
    window = open_window(url, profile)
    started = time.time()
    try:
        while True:
            time.sleep(1)
            window_open = window is not None and window.poll() is None
            if should_end(wb, started, time.time(), window_open):
                break
    except KeyboardInterrupt:
        pass
    httpd.shutdown()
    httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
