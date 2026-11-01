"""生物、法术、装备物理专用 Workbench 的本地服务器与任务管理。"""
from __future__ import annotations

import copy
import json
import mimetypes
import os
import re
import threading
import time
import traceback
import urllib.parse
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import deps
from . import physics as PH
from . import pick as P

STATIC = os.path.join(os.path.dirname(__file__), "static")


def install_root() -> str:
    """返回源码仓库或 Windows 发布包根目录（EXE 所在目录）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    if os.path.isfile(os.path.join(here, "VERSION")):
        return os.path.dirname(root)
    return root


INSTALL_ROOT = install_root()
# 便携配置：不再依赖或在用户主目录创建 .retroport。
SETTINGS_PATH = os.path.join(INSTALL_ROOT, "model-physics.json")
DEFAULT_DATA_DIR = os.path.join(INSTALL_ROOT, "data")
LEGACY_SETTINGS_PATH = os.path.join(
    os.path.expanduser("~"), ".retroport", "creature-physics.json"
)
LEGACY_DATA_DIR = os.path.join(os.path.dirname(LEGACY_SETTINGS_PATH), "creature-physics")
PORT = 8336
APP_NAME = "Retroport Model Physics"


def code_stamp() -> float:
    newest = 0.0
    for folder in (os.path.dirname(os.path.abspath(__file__)), STATIC):
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            if os.path.isfile(path) and name.endswith((".py", ".js", ".html", ".css")):
                newest = max(newest, os.path.getmtime(path))
    return newest


STARTED_CODE = code_stamp()


def app_info() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    try:
        with open(os.path.join(here, "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()
        home = os.path.dirname(root)
    except OSError:
        home = root
        try:
            with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as fh:
                match = re.search(r'^version\s*=\s*"([^"]+)"', fh.read(), re.M)
            version = (match.group(1) if match else "?") + " (source)"
        except OSError:
            version = "?"
    return {"name": APP_NAME, "version": version, "from": home, "code": STARTED_CODE}


@dataclass
class Settings:
    data: str = ""                 # 自定义数据根目录；空值使用程序目录下的 data
    input: str = ""
    phys_dir: str = ""
    output: str = ""
    prefix: str = ""
    recursive: bool = True
    kind: str = "creature"

    @classmethod
    def load(cls, path: str | None = None) -> "Settings":
        # 不能把关路径写成默认参数：默认参数会在函数定义时绑定，测试或嵌入启动时
        # 修改 SETTINGS_PATH 就不会生效。每次调用都读取当前配置路径。
        target = path or SETTINGS_PATH
        try:
            with open(target, encoding="utf-8") as fh:
                raw = json.load(fh)
            return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
        except FileNotFoundError:
            if path is not None:
                return cls()
        except (OSError, ValueError, TypeError):
            return cls()

        # 仅迁移一次旧版设置；旧目录只读不建，新设置始终保存在 EXE 旁边。
        try:
            with open(LEGACY_SETTINGS_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)
            settings = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})
            if os.path.normcase(settings.data_dir) == os.path.normcase(LEGACY_DATA_DIR):
                settings.data = ""
            if os.path.normcase(settings.output) == os.path.normcase(os.path.join(LEGACY_DATA_DIR, "output")):
                settings.output = ""
            try:
                settings.save(target)
            except OSError:
                pass
            return settings
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: str | None = None) -> None:
        target = path or SETTINGS_PATH
        os.makedirs(os.path.dirname(target), exist_ok=True)
        part = target + ".part"
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
        os.replace(part, target)

    @property
    def data_dir(self) -> str:
        if self.data.strip():
            return os.path.abspath(os.path.expanduser(self.data.strip().strip('"')))
        return DEFAULT_DATA_DIR

    @property
    def effective_output(self) -> str:
        return self.output or os.path.join(self.data_dir, "output")

    def update(self, values: dict) -> None:
        old_data = self.data_dir
        old_default_output = os.path.join(old_data, "output")
        follow_default = not self.output or os.path.normcase(self.output) == os.path.normcase(old_default_output)
        for key in ("data", "input", "phys_dir", "output", "prefix"):
            if key in values:
                setattr(self, key, str(values[key] or "").strip())
        if "recursive" in values:
            self.recursive = bool(values["recursive"])
        if "kind" in values:
            kind = str(values["kind"])
            if kind not in PH.TABLES:
                raise PH.PhysicsError(f"未知物理表类型：{kind}")
            self.kind = kind
        # 数据根目录变化时，默认输出一起移动；用户明确设置的自定义输出保持不变。
        if "data" in values and self.data_dir != old_data and follow_default:
            self.output = ""
        self.save()


class Workbench:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.log: list[str] = []
        self.job: dict = {"name": "", "state": "idle"}
        self.last_hello = self.last_bye = 0.0
        self.quitting = False
        self._lock = threading.Lock()

    @property
    def tools(self) -> str:
        return os.path.dirname(deps.entry(self.settings.data_dir, "equip-plus"))

    def busy(self) -> bool:
        with self._lock:
            return self.job.get("state") == "running"

    def say(self, message: str) -> None:
        with self._lock:
            self.log.append(f"{time.strftime('%H:%M:%S')} {message}")
            del self.log[:-300]

    def status(self) -> dict:
        with self._lock:
            job = copy.deepcopy(self.job)
            log = list(self.log)
        values = asdict(self.settings)
        values["data"] = self.settings.data_dir
        values["output"] = self.settings.effective_output
        return {"app": app_info(), "settings": values, "data_dir": self.settings.data_dir,
                "tools": {"downloaded": deps.have(self.settings.data_dir, "equip-plus"),
                          "path": self.tools, "ref": deps.PINNED["equip-plus"]["ref"]},
                "tables": PH.TABLES, "table_labels": PH.TABLE_LABELS,
                "job": job, "log": log, "picker": P.available()}

    def _start(self, name: str, fn) -> None:
        with self._lock:
            if self.job.get("state") == "running":
                raise RuntimeError("已有任务正在运行，请等待完成")
            self.job = {"name": name, "state": "running", "started": time.time()}

        def run():
            try:
                result = fn(self.say)
                with self._lock:
                    self.job.update(state="ok", result=result, ended=time.time())
                self.say(f"{name}完成")
            except Exception as e:
                traceback.print_exc()
                with self._lock:
                    self.job.update(state="failed", error=str(e), ended=time.time())
                self.say(f"{name}失败：{e}")

        threading.Thread(target=run, name="physics-job", daemon=True).start()

    def scan(self) -> None:
        st = self.settings
        self._start("扫描", lambda say: PH.scan(st.input, st.phys_dir, st.recursive, st.prefix))

    def download(self) -> None:
        self._start("下载物理工具", lambda say: {"path": deps.fetch(self.settings.data_dir, "equip-plus", say)})

    def generate(self) -> None:
        st = self.settings

        def run(say):
            if not deps.have(st.data_dir, "equip-plus"):
                deps.fetch(st.data_dir, "equip-plus", say)
            return PH.generate(self.tools, st.input, st.effective_output, st.phys_dir, st.recursive, st.prefix,
                               say, kind=st.kind)

        self._start("生成物理表", run)

    def open_output(self) -> str:
        folder = self.settings.effective_output
        os.makedirs(folder, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
            return folder
        raise RuntimeError("自动打开文件夹仅支持 Windows；请手动打开输出目录")


def make_handler(wb: Workbench):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CreaturePhysics/0.1"

        def log_message(self, _fmt, *_args):
            pass

        def _send(self, body: bytes, content_type="application/json; charset=utf-8", status=200):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value, status=200):
            self._send(json.dumps(value, ensure_ascii=False).encode("utf-8"), status=status)

        def _body(self) -> dict:
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("无效的请求长度")
            if size > 2 << 20:
                raise ValueError("请求过大")
            raw = self.rfile.read(size) if size else b"{}"
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("请求必须是 JSON 对象")
            return value

        def do_GET(self):
            try:
                url = urllib.parse.urlsplit(self.path)
                if url.path == "/":
                    return self._static("index.html")
                if url.path.startswith("/static/"):
                    return self._static(url.path[len("/static/"):])
                if url.path == "/api/status":
                    return self._json(wb.status())
                if url.path == "/api/meta":
                    return self._json(app_info())
                raise LookupError("接口不存在")
            except Exception as e:
                self._error(e)

        def do_POST(self):
            try:
                path = urllib.parse.urlsplit(self.path).path
                body = self._body()
                if path == "/api/settings":
                    wb.settings.update(body)
                    return self._json(wb.status())
                if path == "/api/pick":
                    kind = body.get("kind")
                    folder = kind in ("input-folder", "phys", "output", "data")
                    title = {"model": "选择 M2 或 PHYS 文件", "input-folder": "选择模型目录",
                             "phys": "选择 PFID 对应的 PHYS 目录", "output": "选择输出目录",
                             "data": "选择物理工具与缓存的数据根目录"}.get(kind, "选择路径")
                    patterns = [("模型或物理文件", "*.m2;*.phys"), ("所有文件", "*.*")]
                    chosen = P.pick(folder=folder, title=title, patterns=None if folder else patterns)
                    return self._json({"path": chosen})
                if path == "/api/scan":
                    wb.settings.update(body)
                    wb.scan()
                    return self._json(wb.status())
                if path == "/api/tools/download":
                    # 点击下载也必须先保存当前界面路径，避免与输入框 change 事件竞争。
                    wb.settings.update(body)
                    wb.download()
                    return self._json(wb.status())
                if path == "/api/generate":
                    wb.settings.update(body)
                    wb.generate()
                    return self._json(wb.status())
                if path == "/api/open-output":
                    return self._json({"path": wb.open_output()})
                if path == "/api/hello":
                    wb.last_hello = time.time()
                    return self._json({"ok": True})
                if path == "/api/bye":
                    wb.last_bye = time.time()
                    return self._json({"ok": True})
                if path == "/api/quit":
                    wb.quitting = True
                    return self._json({"ok": True})
                raise LookupError("接口不存在")
            except Exception as e:
                self._error(e)

        def _static(self, rel: str):
            full = os.path.realpath(os.path.join(STATIC, rel))
            root = os.path.realpath(STATIC)
            if not full.startswith(root + os.sep) or not os.path.isfile(full):
                raise LookupError("静态文件不存在")
            with open(full, "rb") as fh:
                body = fh.read()
            content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if content_type.startswith("text/") or content_type.endswith("javascript"):
                content_type += "; charset=utf-8"
            self._send(body, content_type)

        def _error(self, error: Exception):
            if isinstance(error, (LookupError, FileNotFoundError)):
                status = 404
            elif isinstance(error, (PH.PhysicsError, ValueError)):
                status = 400
            elif isinstance(error, RuntimeError):
                status = 409
            else:
                status = 500
            self._json({"error": str(error)}, status)

    return Handler


class _Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def start_server(settings: Settings, port: int = PORT) -> tuple[_Server, Workbench]:
    wb = Workbench(settings)
    return _Server(("127.0.0.1", port), make_handler(wb)), wb


def serve(settings: Settings, port: int = PORT, open_browser: bool = True, log=print) -> None:
    httpd, wb = start_server(settings, port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    # 发布自检可能使用 Windows 的 cp1252 控制台；启动日志保持 ASCII，避免编码失败。
    log(f"Model Physics Workbench: {url} (Ctrl+C to stop)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
