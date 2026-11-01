import os
import struct

import pytest

from retroport.workbench import physics as PH


def chunk(tag, payload=b""):
    return tag + struct.pack("<I", len(payload)) + payload


def md21(*chunks):
    return chunk(b"MD21", b"MD20" + struct.pack("<I", 300)) + b"".join(chunks)


def encoded_row(key, marker=b""):
    """构造结构有效的 PHY2 行；合并测试不需要真实物理体。"""
    raw = key.encode("latin-1")
    row = bytearray(struct.pack("<H", len(raw)) + raw)
    while len(row) % 4:
        row.append(0)
    row += bytes(4) + marker
    while len(row) % 4:
        row.append(0)
    return bytes(row)


def table_bytes(*keys):
    return PH.write_table({key: encoded_row(key) for key in keys})


def test_phys_bytes_reads_inline_pfdc():
    assert PH.phys_bytes(md21(chunk(b"PFDC", b"physics")), lambda fdid: b"") == b"physics"


def test_phys_bytes_reads_external_pfid():
    assert PH.phys_bytes(md21(chunk(b"PFID", struct.pack("<I", 123))), lambda fdid: b"external") == b"external"


def test_md20_has_no_retail_physics():
    assert PH.phys_bytes(b"MD20" + bytes(20), lambda fdid: b"") is None


def test_scan_classifies_models_and_external_phys(tmp_path):
    models = tmp_path / "models"
    phys = tmp_path / "phys"
    models.mkdir()
    phys.mkdir()
    (models / "inline.m2").write_bytes(md21(chunk(b"PFDC", b"inline")))
    (models / "external.m2").write_bytes(md21(chunk(b"PFID", struct.pack("<I", 456))))
    (models / "none.m2").write_bytes(md21())
    (models / "old.m2").write_bytes(b"MD20" + bytes(20))
    (phys / "456.phys").write_bytes(b"external")

    result = PH.scan(str(models), str(phys), prefix="creature/custom")
    assert (result["total"], result["ready"], result["none"], result["failed"]) == (4, 2, 2, 0)
    inline = next(i for i in result["items"] if i["name"] == "inline.m2")
    assert inline["state"] == "ready"
    assert inline["source"] == "M2 内嵌 PFDC"
    assert "creature\\custom\\inline.m2" in inline["keys"]
    assert "inline.m2" in inline["keys"]
    external = next(i for i in result["items"] if i["name"] == "external.m2")
    assert external["state"] == "ready"
    assert "PFID 456" in external["source"]


def test_missing_external_phys_is_reported(tmp_path):
    path = tmp_path / "missing.m2"
    path.write_bytes(md21(chunk(b"PFID", struct.pack("<I", 999))))
    result = PH.scan(str(path))
    assert result["ready"] == 0
    assert "999.phys" in result["items"][0]["source"]


def test_standalone_phys_becomes_m2_key(tmp_path):
    path = tmp_path / "dragon.phys"
    path.write_bytes(b"physics")
    result = PH.scan(str(path))
    assert result["ready"] == 1
    assert result["items"][0]["keys"] == ["dragon.m2"]


def test_generate_keeps_a_when_adding_b_and_backs_up_old_table(tmp_path, monkeypatch):
    model = tmp_path / "b.m2"
    model.write_bytes(md21(chunk(b"PFDC", b"physics")))
    output = tmp_path / "out"
    table = output / "DBFilesClient" / "WXLCreaturePhysics.phy2"
    table.parent.mkdir(parents=True)
    old_table = table_bytes("a.m2")
    table.write_bytes(old_table)

    def fake_run(tools, job):
        assert len(job["items"]) == 1
        assert job["items"][0]["keys"] == ["b.m2"]
        return {"rows": 1, "notes": [], "table": table_bytes("b.m2")}

    monkeypatch.setattr(PH, "_run", fake_run)
    result = PH.generate("unused", str(model), str(output), say=lambda message: None)

    assert set(PH.read_table(table.read_bytes())) == {"a.m2", "b.m2"}
    assert result["rows"] == 2
    assert (result["kept"], result["added"], result["updated"]) == (1, 1, 0)
    assert open(result["backup"], "rb").read() == old_table


def test_generate_rejects_input_without_physics(tmp_path):
    model = tmp_path / "none.m2"
    model.write_bytes(md21())
    with pytest.raises(PH.PhysicsError, match="没有可生成"):
        PH.generate("unused", str(model), str(tmp_path / "out"))


@pytest.mark.parametrize("kind,filename,label", [
    ("creature", "WXLCreaturePhysics.phy2", "生物"),
    ("spell", "WXLSpellPhysics.phy2", "法术"),
    ("equipment", "WXLEquipPlusPhysics.phy2", "装备"),
])
def test_generate_supports_creature_spell_and_equipment(tmp_path, monkeypatch, kind, filename, label):
    model = tmp_path / "model.m2"
    model.write_bytes(md21(chunk(b"PFDC", b"physics")))
    monkeypatch.setattr(PH, "_run", lambda tools, job: {"rows": 1, "notes": [], "table": table_bytes("model.m2")})
    result = PH.generate("unused", str(model), str(tmp_path / "out"), say=lambda message: None, kind=kind)
    assert result["kind"] == kind
    assert result["kind_label"] == label
    assert result["table_name"] == filename
    assert set(PH.read_table(open(result["table"], "rb").read())) == {"model.m2"}
    assert os.path.basename(result["table"]) == filename


def test_generate_rejects_unknown_table_type(tmp_path):
    with pytest.raises(PH.PhysicsError, match="未知物理表类型"):
        PH.generate("unused", str(tmp_path), str(tmp_path), kind="unknown")


def test_generate_updates_same_key_without_duplicating_it(tmp_path, monkeypatch):
    model = tmp_path / "a.m2"
    model.write_bytes(md21(chunk(b"PFDC", b"physics")))
    output = tmp_path / "out"
    table = output / "DBFilesClient" / "WXLCreaturePhysics.phy2"
    table.parent.mkdir(parents=True)
    table.write_bytes(PH.write_table({"a.m2": encoded_row("a.m2", b"old")}))
    new_row = encoded_row("a.m2", b"new")
    monkeypatch.setattr(PH, "_run", lambda tools, job: {
        "rows": 1, "notes": [], "table": PH.write_table({"a.m2": new_row})
    })

    result = PH.generate("unused", str(model), str(output), say=lambda message: None)
    rows = PH.read_table(table.read_bytes())

    assert rows == {"a.m2": new_row}
    assert result["rows"] == 1
    assert (result["kept"], result["added"], result["updated"]) == (0, 0, 1)


def test_invalid_existing_table_is_not_backed_up_or_overwritten(tmp_path, monkeypatch):
    model = tmp_path / "b.m2"
    model.write_bytes(md21(chunk(b"PFDC", b"physics")))
    output = tmp_path / "out"
    table = output / "DBFilesClient" / "WXLCreaturePhysics.phy2"
    table.parent.mkdir(parents=True)
    table.write_bytes(b"broken")
    monkeypatch.setattr(PH, "_run", lambda tools, job: {
        "rows": 1, "notes": [], "table": table_bytes("b.m2")
    })

    with pytest.raises(PH.PhysicsError, match="PHY2"):
        PH.generate("unused", str(model), str(output), say=lambda message: None)

    assert table.read_bytes() == b"broken"
    assert not list(table.parent.glob("*.bak-*"))
    assert not (table.parent / (table.name + ".part")).exists()
