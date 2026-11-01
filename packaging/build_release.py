"""构建 Windows 生物／法术／装备物理专用版：EXE 启动器、独立 Python runtime 和 app。

用法：python packaging/build_release.py --out dist
必须在 Windows 上运行。发布包不包含 Equip Plus；首次生成时由程序自行下载。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
NAME = "Model Physics Workbench"
ARCHIVE = "Model-Physics-Workbench"
PYTHON = "3.14.2"
PYTHON_SHA256 = "f05e28d161c6b15af64a7cb7f08b4a22b3a6b03eee71baee24ea557b3bdd5798"
CSC = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe")


def say(message: str) -> None:
    """GitHub 的 Windows Python 可能使用 cp1252；任何构建日志都不能因此中断发布。"""
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        safe = message.encode(encoding, errors="backslashreplace").decode(encoding)
        print(safe, flush=True)


def version() -> str:
    for line in open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8"):
        if line.startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    return "0"


def download(url: str, dest: str, sha256: str = "") -> str:
    if not os.path.isfile(dest):
        say(f"  downloading {url}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "creature-physics-release"})
        with urllib.request.urlopen(request, timeout=120) as response, open(dest + ".part", "wb") as fh:
            shutil.copyfileobj(response, fh)
        os.replace(dest + ".part", dest)
    with open(dest, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    say(f"  {os.path.basename(dest)}: sha256 {digest}")
    if sha256 and digest != sha256:
        os.remove(dest)
        raise SystemExit(f"{os.path.basename(dest)} 的 SHA256 不匹配，已删除")
    return dest


def icon(dest: str) -> str:
    from PIL import Image
    image = Image.open(os.path.join(REPO, "retroport", "workbench", "static", "icon.png")).convert("RGBA")
    image.save(dest, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return dest


def launcher(dest_exe: str, work: str) -> None:
    if not os.path.isfile(CSC):
        raise SystemExit(f"找不到 Windows 自带 C# 编译器：{CSC}")
    ico = icon(os.path.join(work, "icon.ico"))
    command = [CSC, "/nologo", "/target:winexe", "/optimize+", f"/win32icon:{ico}", f"/out:{dest_exe}",
               "/reference:System.Windows.Forms.dll", os.path.join(HERE, "launcher.cs")]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"启动器编译失败：\n{result.stdout}{result.stderr}")
    say(f"  {dest_exe}")


def copy_tree(src: str, dest: str) -> None:
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"))


def runtime(dest: str, cache: str) -> None:
    url = f"https://www.python.org/ftp/python/{PYTHON}/python-{PYTHON}-embed-amd64.zip"
    with zipfile.ZipFile(download(url, os.path.join(cache, os.path.basename(url)), PYTHON_SHA256)) as archive:
        archive.extractall(dest)
    short = "".join(PYTHON.split(".")[:2])
    with open(os.path.join(dest, f"python{short}._pth"), "w", encoding="utf-8") as fh:
        fh.write(f"python{short}.zip\n.\n..\\app\nimport site\n")


def app(dest: str, ver: str) -> None:
    copy_tree(os.path.join(REPO, "retroport"), os.path.join(dest, "retroport"))
    with open(os.path.join(dest, "retroport", "workbench", "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(ver + "\n")


def notices(dest: str) -> None:
    licenses = os.path.join(dest, "licenses")
    os.makedirs(licenses, exist_ok=True)
    for src, name in ((os.path.join(REPO, "LICENSE"), "retroport.txt"),
                      (os.path.join(dest, "runtime", "LICENSE.txt"), "python.txt")):
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(licenses, name))
    shutil.copy2(os.path.join(REPO, "THIRD_PARTY_NOTICES.md"), os.path.join(dest, "THIRD_PARTY_NOTICES.md"))
    shutil.copy2(os.path.join(HERE, "README.txt"), os.path.join(dest, "README.txt"))


def check(dest: str) -> None:
    py = os.path.join(dest, "runtime", "python.exe")
    code = "import retroport.workbench.app, retroport.workbench.physics; print('imports ok')"
    result = subprocess.run([py, "-c", code], capture_output=True, text=True, cwd=dest)
    if result.returncode != 0:
        raise SystemExit(f"发布包 Python 导入失败：\n{result.stdout}{result.stderr}")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    home = os.path.join(dest, "..", "check-home")
    shutil.rmtree(home, ignore_errors=True)
    env = dict(os.environ, USERPROFILE=os.path.abspath(home), HOME=os.path.abspath(home), PYTHONIOENCODING="utf-8")
    serve = f"from retroport.workbench import server as S; S.serve(S.Settings(), port={port}, open_browser=False)"
    process = subprocess.Popen([py, "-c", serve], cwd=dest, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=2) as response:
                    meta = json.load(response)
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
                    page = response.read()
                if meta.get("name") == "Retroport Model Physics" and b"Retroport" in page:
                    say("  发布包页面与接口检查通过")
                    return
            except OSError:
                if process.poll() is not None:
                    break
        raise SystemExit(f"发布包没有正常响应：\n{process.stdout.read().decode(errors='replace')}")
    finally:
        process.kill()
        shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    # 同时保护 argparse、异常和其他不经过 say() 的控制台输出。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, OSError):
            pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(REPO, "dist"))
    parser.add_argument("--launcher-only", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("发布包必须在 Windows 上构建")
    work = os.path.join(args.out, "work")
    os.makedirs(work, exist_ok=True)
    if args.launcher_only:
        launcher(os.path.join(REPO, f"{NAME}.exe"), work)
        return 0
    ver = version()
    dest = os.path.join(args.out, NAME)
    if os.path.exists(dest):
        old = dest + ".old"
        shutil.rmtree(old, ignore_errors=True)
        os.rename(dest, old)
        shutil.rmtree(old)
    os.makedirs(dest)
    say(f"Building {NAME} {ver}")
    runtime(os.path.join(dest, "runtime"), os.path.join(args.out, "cache"))
    app(os.path.join(dest, "app"), ver)
    notices(dest)
    launcher(os.path.join(dest, f"{NAME}.exe"), work)
    check(dest)
    archive = os.path.join(args.out, f"{ARCHIVE}-{ver}-win64.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for folder, _dirs, files in os.walk(dest):
            for name in files:
                full = os.path.join(folder, name)
                z.write(full, os.path.join(NAME, os.path.relpath(full, dest)))
    say(f"完成：{archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
