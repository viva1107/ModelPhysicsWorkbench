"""按需下载 Equip Plus 的物理表工具；发布包不捆绑该外部项目。"""
from __future__ import annotations

import io
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
import zipfile

PINNED = {
    "equip-plus": {
        "repo": "TheDaveCalaz/wxl-equip-plus",
        "ref": "ac7440c0db407b1dceb3573aa211cb6de68ee7c6",
        "entry": os.path.join("tools", "physics_table.py"),
        "label": "Equip Plus 物理工具",
    }
}
_lock = threading.Lock()


def folder(data_dir: str, name: str) -> str:
    return os.path.join(data_dir, "deps", name)


def entry(data_dir: str, name: str) -> str:
    return os.path.join(folder(data_dir, name), PINNED[name]["entry"])


def have(data_dir: str, name: str) -> bool:
    try:
        with open(os.path.join(folder(data_dir, name), ".retroport-ref"), encoding="utf-8") as fh:
            ref = fh.read().strip()
    except OSError:
        return False
    return ref == PINNED[name]["ref"] and os.path.isfile(entry(data_dir, name))


def http_get(url: str, dest: str) -> None:
    last = None
    for attempt in range(3):
        part = dest + ".part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "retroport-creature-physics/0.1"})
            with urllib.request.urlopen(req, timeout=120) as response:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(part, "wb") as fh:
                    shutil.copyfileobj(response, fh)
            os.replace(part, dest)
            return
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            try:
                os.remove(part)
            except OSError:
                pass
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    reason = getattr(last, "reason", None) or last
    raise RuntimeError(f"下载失败：{reason}。请检查网络或 GitHub 访问。")


def fetch(data_dir: str, name: str, say=print, get=http_get) -> str:
    """下载固定提交并解压；已存在相同提交时直接返回。"""
    p = PINNED[name]
    with _lock:
        if have(data_dir, name):
            return entry(data_dir, name)
        url = f"https://codeload.github.com/{p['repo']}/zip/{p['ref']}"
        say(f"正在从 github.com/{p['repo']} 下载{p['label']}（{p['ref'][:7]}）")
        tmp = os.path.join(data_dir, "deps", f"{name}.zip")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        get(url, tmp)
        dest, part = folder(data_dir, name), folder(data_dir, name) + ".part"
        shutil.rmtree(part, ignore_errors=True)
        try:
            with open(tmp, "rb") as fh:
                unpack(fh.read(), part)
            with open(os.path.join(part, ".retroport-ref"), "w", encoding="utf-8") as fh:
                fh.write(p["ref"])
            shutil.rmtree(dest, ignore_errors=True)
            os.replace(part, dest)
        finally:
            shutil.rmtree(part, ignore_errors=True)
            try:
                os.remove(tmp)
            except OSError:
                pass
        if not have(data_dir, name):
            raise RuntimeError(f"下载包中缺少 {p['entry']}")
        say(f"物理工具已下载到：{dest}")
        return entry(data_dir, name)


def unpack(data: bytes, dest: str) -> None:
    """安全解压 GitHub ZIP，去掉顶层目录，拒绝目录穿越。"""
    root = os.path.realpath(dest)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            parts = info.filename.replace("\\", "/").split("/")[1:]
            if not parts or not parts[-1] and len(parts) == 1:
                continue
            target = os.path.realpath(os.path.join(dest, *parts))
            if target != root and not target.startswith(root + os.sep):
                raise RuntimeError(f"压缩包包含越界路径：{info.filename}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
