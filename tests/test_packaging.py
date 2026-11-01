import contextlib
import importlib.util
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_module():
    spec = importlib.util.spec_from_file_location("release_build", ROOT / "packaging" / "build_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parent_build_log_supports_cp1252():
    release = release_module()
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    with contextlib.redirect_stdout(stream):
        release.say("  发布包页面与接口检查通过")
    stream.flush()
    output = stream.buffer.getvalue()
    assert b"\\u53d1\\u5e03" in output


def test_actions_forces_utf8_for_parent_and_children():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "PYTHONIOENCODING: utf-8" in workflow
    build = (ROOT / "packaging" / "build_release.py").read_text(encoding="utf-8")
    assert 'PYTHONIOENCODING="utf-8"' in build
