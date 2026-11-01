import json
import os
import struct
import threading
import time
import urllib.request

from retroport.workbench import server as S


def request(url, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, response.read()


def test_server_serves_physics_only_page_and_scans(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    md20 = b"MD20" + struct.pack("<I", 300)
    body = struct.pack("<I", len(md20)) + md20 + b"PFDC" + struct.pack("<I", 4) + b"phys"
    model = tmp_path / "dragon.m2"
    model.write_bytes(b"MD21" + body)
    settings = S.Settings(input=str(model), output=str(tmp_path / "out"))
    httpd, wb = S.start_server(settings, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, meta = request(base + "/api/meta")
        assert status == 200
        assert json.loads(meta)["name"] == S.APP_NAME
        status, page = request(base + "/")
        assert status == 200
        assert "生物、法术、装备物理表生成" in page.decode("utf-8")
        assert "WXLSpellPhysics.phy2" in page.decode("utf-8")
        assert "WXLEquipPlusPhysics.phy2" in page.decode("utf-8")
        status, _ = request(base + "/api/scan", {"input": str(model)})
        assert status == 200
        for _ in range(50):
            if wb.job.get("state") == "ok":
                break
            time.sleep(0.02)
        assert wb.job["state"] == "ok"
        assert wb.job["result"]["ready"] == 1
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_serve_startup_log_supports_cp1252(monkeypatch):
    """GitHub Windows 发布自检使用 cp1252 时，启动日志也不能让服务器退出。"""
    import io

    class FakeServer:
        server_address = ("127.0.0.1", 8336)
        closed = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    fake = FakeServer()
    monkeypatch.setattr(S, "start_server", lambda settings, port: (fake, None))
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    S.serve(S.Settings(), open_browser=False, log=lambda message: print(message, file=stream))
    stream.flush()
    assert b"Model Physics Workbench" in stream.buffer.getvalue()
    assert fake.closed


def test_custom_data_root_persists_and_moves_default_output(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    settings = S.Settings()
    old_default = settings.effective_output
    custom = tmp_path / "custom-data"
    settings.update({"data": str(custom), "output": old_default})

    assert settings.data_dir == str(custom)
    assert settings.effective_output == str(custom / "output")
    loaded = S.Settings.load()
    assert loaded.data_dir == str(custom)
    assert loaded.effective_output == str(custom / "output")
    wb = S.Workbench(loaded)
    assert wb.tools.startswith(str(custom))


def test_custom_data_root_keeps_explicit_output(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    output = tmp_path / "separate-output"
    settings = S.Settings(output=str(output))
    settings.update({"data": str(tmp_path / "new-data"), "output": str(output)})
    assert settings.effective_output == str(output)


def test_settings_and_default_data_are_portable():
    assert S.SETTINGS_PATH == os.path.join(S.INSTALL_ROOT, "model-physics.json")
    assert S.DEFAULT_DATA_DIR == os.path.join(S.INSTALL_ROOT, "data")
    assert ".retroport" not in S.SETTINGS_PATH
    assert ".retroport" not in S.DEFAULT_DATA_DIR


def test_legacy_custom_root_migrates_to_portable_settings(tmp_path, monkeypatch):
    legacy = tmp_path / "old-home" / ".retroport" / "creature-physics.json"
    legacy.parent.mkdir(parents=True)
    custom = tmp_path / "desktop" / "Model Physics Workbench"
    legacy.write_text(json.dumps({"data": str(custom), "kind": "spell"}), encoding="utf-8")
    portable = tmp_path / "new-app" / "model-physics.json"
    monkeypatch.setattr(S, "SETTINGS_PATH", str(portable))
    monkeypatch.setattr(S, "DEFAULT_DATA_DIR", str(tmp_path / "new-app" / "data"))
    monkeypatch.setattr(S, "LEGACY_SETTINGS_PATH", str(legacy))
    monkeypatch.setattr(S, "LEGACY_DATA_DIR", str(legacy.parent / "creature-physics"))

    loaded = S.Settings.load()

    assert loaded.data_dir == str(custom)
    assert loaded.kind == "spell"
    assert portable.is_file()
    assert S.Settings.load().data_dir == str(custom)


def test_download_saves_current_data_root_before_start(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    custom = tmp_path / "custom-download-root"
    seen = []
    httpd, wb = S.start_server(S.Settings(), port=0)
    monkeypatch.setattr(wb, "download", lambda: seen.append(wb.settings.data_dir))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        status, _ = request(base + "/api/tools/download", {"data": str(custom)})
        assert status == 200
        assert seen == [str(custom)]
        assert S.Settings.load().data_dir == str(custom)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
