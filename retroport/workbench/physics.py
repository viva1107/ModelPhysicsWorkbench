"""从正式服 M2／PHYS 文件生成生物、法术或装备 PHY2 物理表。

只保留物理所需的功能：读取 MD21 的 PFDC／PFID、收集本地模型、调用
Equip Plus 的 physics_table.py，并安全写出物理表。不转换模型，也不修改
客户端、DBC、SQL 或服务端。
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import time

TABLES = {
    "creature": "WXLCreaturePhysics.phy2",
    "spell": "WXLSpellPhysics.phy2",
    "equipment": "WXLEquipPlusPhysics.phy2",
}
TABLE_LABELS = {"creature": "生物", "spell": "法术", "equipment": "装备"}
CREATURE_TABLE = "DBFilesClient\\" + TABLES["creature"]
SPELL_TABLE = "DBFilesClient\\" + TABLES["spell"]
EQUIPMENT_TABLE = "DBFilesClient\\" + TABLES["equipment"]
JOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "physics_job.py")


class PhysicsError(Exception):
    """可以向界面直接显示的物理处理错误。"""


def python_exe() -> str:
    """pythonw 启动时使用同目录的 python.exe，以便读取工具错误输出。"""
    exe = sys.executable
    if os.path.basename(exe).lower() == "pythonw.exe":
        twin = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(twin):
            return twin
    return exe


def phys_bytes(model: bytes, read) -> bytes | None:
    """返回 MD21 内嵌的 PFDC，或读取 PFID 指向的 .phys；没有物理时返回 None。"""
    if model[:4] == b"MD20":
        return None
    pos, pfid = 0, 0
    while pos + 8 <= len(model):
        tag = model[pos:pos + 4]
        size = struct.unpack_from("<I", model, pos + 4)[0]
        if size > len(model) - pos - 8:
            raise PhysicsError("M2 块长度超出文件末尾，文件可能已损坏")
        if tag == b"PFDC":
            return model[pos + 8:pos + 8 + size]
        if tag == b"PFID" and size >= 4:
            pfid = struct.unpack_from("<I", model, pos + 8)[0]
        pos += 8 + size
    if not pfid:
        return None
    try:
        return read(pfid)
    except Exception:
        return None


def _client_path(path: str) -> str:
    return path.replace("/", "\\").strip("\\")


def _norm_key(path: str) -> str:
    key = path.replace("/", "\\").lower()
    if key.endswith((".mdx", ".mdl")):
        key = key[:-4] + ".m2"
    return key


def _fnv1a(key: str) -> int:
    value = 0x811C9DC5
    for byte in key.encode("latin-1"):
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def read_table(blob: bytes) -> dict[str, bytes]:
    """读取 PHY2 的索引和原始行；旧行无需反序列化物理体即可原样保留。"""
    if len(blob) < 8 or blob[:4] != b"PHY2":
        raise PhysicsError("现有文件不是有效的 PHY2 物理表")
    count = struct.unpack_from("<I", blob, 4)[0]
    index_end = 8 + count * 8
    if index_end > len(blob):
        raise PhysicsError("现有 PHY2 索引超出文件末尾，文件可能已损坏")
    entries = []
    for i in range(count):
        hash_value, offset = struct.unpack_from("<II", blob, 8 + i * 8)
        if offset < index_end or offset >= len(blob):
            raise PhysicsError("现有 PHY2 包含无效的记录偏移，已停止合并")
        entries.append((hash_value, offset))
    entries.sort(key=lambda entry: entry[1])
    rows = {}
    for i, (hash_value, offset) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else len(blob)
        if end <= offset or offset + 2 > end:
            raise PhysicsError("现有 PHY2 的记录范围无效，已停止合并")
        row = blob[offset:end]
        key_length = struct.unpack_from("<H", row, 0)[0]
        if 2 + key_length > len(row):
            raise PhysicsError("现有 PHY2 的记录键超出行末尾，已停止合并")
        try:
            key = _norm_key(row[2:2 + key_length].decode("latin-1"))
        except UnicodeDecodeError:
            raise PhysicsError("现有 PHY2 的记录键无法读取，已停止合并") from None
        if not key or _fnv1a(key) != hash_value:
            raise PhysicsError("现有 PHY2 的记录键或校验值无效，已停止合并")
        if key in rows:
            raise PhysicsError(f"现有 PHY2 包含重复记录键：{key}")
        rows[key] = row
    return rows


def write_table(rows: dict[str, bytes]) -> bytes:
    """按 Equip Plus 的 PHY2 格式重写索引，记录内容保持原始字节。"""
    items = sorted((_fnv1a(key), key, row) for key, row in rows.items())
    header = bytearray(b"PHY2" + struct.pack("<I", len(items)))
    body = bytearray()
    base = 8 + len(items) * 8
    for hash_value, _key, row in items:
        header += struct.pack("<II", hash_value, base + len(body))
        body += row
    return bytes(header + body)


def merge_tables(existing: bytes, new: bytes) -> tuple[bytes, dict]:
    """保留旧表记录；新表追加新键，并更新与新表完全相同的旧键。"""
    old_rows = read_table(existing)
    new_rows = read_table(new)
    updated = sum(key in old_rows for key in new_rows)
    merged = dict(old_rows)
    merged.update(new_rows)
    stats = {"existing_rows": len(old_rows), "generated_rows": len(new_rows),
             "added": len(new_rows) - updated, "updated": updated,
             "kept": len(old_rows) - updated, "rows": len(merged)}
    return write_table(merged), stats


def _keys(root: str, path: str, single: bool, prefix: str) -> list[str]:
    rel = os.path.basename(path) if single else os.path.relpath(path, root)
    if rel.lower().endswith(".phys"):
        rel = rel[:-5] + ".m2"
    rel = _client_path(rel)
    prefix = _client_path(prefix.strip())
    full = _client_path(os.path.join(prefix, rel)) if prefix else rel
    bare = os.path.basename(full)
    keys = []
    for key in (full, rel, bare):
        if key and key not in keys:
            keys.append(key)
    return keys


def _external_phys(model_path: str, phys_dir: str, fdid: int) -> tuple[bytes | None, str]:
    folders = [p for p in (phys_dir, os.path.dirname(model_path)) if p]
    names = (f"{fdid}.phys", str(fdid), os.path.splitext(os.path.basename(model_path))[0] + ".phys")
    for folder in folders:
        for name in names:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                with open(path, "rb") as fh:
                    return fh.read(), path
    return None, ""


def _read_item(path: str, phys_dir: str) -> tuple[bytes | None, str, str]:
    """返回（物理字节、来源说明、状态）；状态为 ready／none。"""
    if path.lower().endswith(".phys"):
        with open(path, "rb") as fh:
            return fh.read(), "独立 PHYS 文件", "ready"
    with open(path, "rb") as fh:
        model = fh.read()
    if model[:4] == b"MD20":
        return None, "WotLK MD20 模型不含正式服物理", "none"
    if model[:4] != b"MD21":
        raise PhysicsError("不是 MD21 正式服模型")

    pos, pfid = 0, 0
    while pos + 8 <= len(model):
        tag = model[pos:pos + 4]
        size = struct.unpack_from("<I", model, pos + 4)[0]
        if size > len(model) - pos - 8:
            raise PhysicsError("M2 块长度超出文件末尾，文件可能已损坏")
        if tag == b"PFDC":
            blob = model[pos + 8:pos + 8 + size]
            return (blob, "M2 内嵌 PFDC", "ready") if blob else (None, "PFDC 为空", "none")
        if tag == b"PFID" and size >= 4:
            pfid = struct.unpack_from("<I", model, pos + 8)[0]
        pos += 8 + size
    if not pfid:
        return None, "没有 PFDC／PFID 物理数据", "none"
    blob, source = _external_phys(path, phys_dir, pfid)
    if blob:
        return blob, f"PFID {pfid}：{source}", "ready"
    return None, f"缺少 PFID {pfid} 对应的 {fdid_name(pfid)}", "none"


def fdid_name(fdid: int) -> str:
    return f"{fdid}.phys"


def scan(input_path: str, phys_dir: str = "", recursive: bool = True, prefix: str = "") -> dict:
    """扫描 M2／PHYS，但不调用外部工具，也不写任何输出文件。"""
    input_path = os.path.abspath(os.path.expanduser((input_path or "").strip().strip('"')))
    phys_dir = os.path.abspath(os.path.expanduser((phys_dir or "").strip().strip('"'))) if phys_dir.strip() else ""
    if not os.path.exists(input_path):
        raise PhysicsError(f"输入路径不存在：{input_path}")
    if phys_dir and not os.path.isdir(phys_dir):
        raise PhysicsError(f"PHYS 目录不存在：{phys_dir}")
    single = os.path.isfile(input_path)
    if single:
        if os.path.splitext(input_path)[1].lower() not in (".m2", ".phys"):
            raise PhysicsError("请选择 .m2 或 .phys 文件")
        root, files = os.path.dirname(input_path), [input_path]
    else:
        root = input_path
        files = []
        if recursive:
            for folder, _dirs, names in os.walk(input_path):
                files.extend(os.path.join(folder, n) for n in names if n.lower().endswith((".m2", ".phys")))
        else:
            files = [os.path.join(input_path, n) for n in os.listdir(input_path)
                     if n.lower().endswith((".m2", ".phys")) and os.path.isfile(os.path.join(input_path, n))]
        files.sort(key=str.lower)
    if not files:
        raise PhysicsError("没有找到 .m2 或 .phys 文件")

    items = []
    for path in files:
        item = {"path": path, "name": os.path.basename(path),
                "keys": _keys(root, path, single, prefix), "bytes": os.path.getsize(path)}
        try:
            blob, source, state = _read_item(path, phys_dir)
            item.update(state=state, source=source, physics_bytes=len(blob or b""))
        except Exception as e:
            item.update(state="error", source=f"{type(e).__name__}: {e}", physics_bytes=0)
        items.append(item)
    ready = sum(i["state"] == "ready" for i in items)
    failed = sum(i["state"] == "error" for i in items)
    return {"root": root, "items": items, "total": len(items), "ready": ready,
            "none": len(items) - ready - failed, "failed": failed}


def _run(tools: str, job: dict) -> dict:
    if not tools or not os.path.isfile(os.path.join(tools, "physics_table.py")):
        raise PhysicsError("物理工具尚未下载，请先点击“下载物理工具”")
    with tempfile.TemporaryDirectory(prefix="creature-physics-") as tmp:
        for i, item in enumerate(job["items"]):
            path = os.path.join(tmp, f"{i}.phys")
            with open(path, "wb") as fh:
                fh.write(item.pop("phys"))
            item["path"] = path
        job["out"] = os.path.join(tmp, "out")
        job_path = os.path.join(tmp, "job.json")
        with open(job_path, "w", encoding="utf-8") as fh:
            json.dump(job, fh)
        try:
            result = subprocess.run([python_exe(), "-I", JOB, tools, job_path], capture_output=True, text=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=300)
        except subprocess.TimeoutExpired:
            raise PhysicsError("物理工具运行超过 5 分钟，已停止") from None
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "physics_job failed").strip()
            raise PhysicsError(detail.splitlines()[-1] if detail else "物理工具运行失败")
        with open(job["out"] + ".json", encoding="utf-8") as fh:
            parsed = json.load(fh)
        if os.path.isfile(job["out"] + ".phy2"):
            with open(job["out"] + ".phy2", "rb") as fh:
                parsed["table"] = fh.read()
        return parsed


def table(tools: str, models: list[tuple]) -> tuple[bytes | None, list[str]]:
    """为（客户端路径列表，.phys 字节）条目生成 PHY2。"""
    items = [{"keys": keys, "phys": blob} for keys, blob in models if blob]
    if not items:
        return None, []
    result = _run(tools, {"mode": "table", "items": items})
    return (result.get("table") if result.get("rows") else None), result.get("notes", [])


def generate(tools: str, input_path: str, output_dir: str, phys_dir: str = "",
             recursive: bool = True, prefix: str = "", say=print, kind: str = "creature") -> dict:
    """生成所选类型的 PHY2；kind 为 creature／spell／equipment。"""
    if kind not in TABLES:
        raise PhysicsError(f"未知物理表类型：{kind}")
    table_name = TABLES[kind]
    found = scan(input_path, phys_dir, recursive, prefix)
    say(f"扫描到 {found['total']} 个文件：{found['ready']} 个有物理，{found['none']} 个无物理，{found['failed']} 个读取失败")
    models = []
    for item in found["items"]:
        if item["state"] != "ready":
            continue
        blob, _source, _state = _read_item(item["path"], phys_dir)
        models.append((item["keys"], blob))
        say(f"读取物理：{item['name']}")
    if not models:
        raise PhysicsError("没有可生成的物理数据；PFID 模型需要把对应 .phys 放入 PHYS 目录")
    result = _run(tools, {"mode": "table", "items": [{"keys": keys, "phys": blob} for keys, blob in models]})
    for note in result.get("notes", []):
        say(f"注意：{note}")
    blob = result.get("table")
    if not result.get("rows") or not blob:
        raise PhysicsError("物理工具没有生成有效记录，请查看日志")
    generated_rows = read_table(blob)
    if not generated_rows:
        raise PhysicsError("物理工具没有生成有效记录，请查看日志")

    output_dir = os.path.abspath(os.path.expanduser((output_dir or "").strip().strip('"')))
    folder = os.path.join(output_dir, "DBFilesClient")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, table_name)
    merge = {"existing_rows": 0, "generated_rows": len(generated_rows),
             "added": len(generated_rows), "updated": 0, "kept": 0,
             "rows": len(generated_rows)}
    if os.path.isfile(dest):
        # 先完整读取并合并，任何旧表解析错误都会在备份或写入之前停止。
        with open(dest, "rb") as fh:
            existing = fh.read()
        blob, merge = merge_tables(existing, blob)
        say(f"合并现有物理表：保留 {merge['kept']} 条，新增 {merge['added']} 条，更新 {merge['updated']} 条")

    backup = ""
    if os.path.isfile(dest):
        backup = dest + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
        counter = 1
        while os.path.exists(backup):
            backup = dest + f".bak-{time.strftime('%Y%m%d-%H%M%S')}-{counter}"
            counter += 1
        os.replace(dest, backup)
        say(f"已备份旧物理表：{backup}")
    part = dest + ".part"
    try:
        with open(part, "wb") as fh:
            fh.write(blob)
        os.replace(part, dest)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    say(f"完成：物理表共 {merge['rows']} 条记录 → {dest}")
    return {"table": dest, "table_name": table_name, "kind": kind, "kind_label": TABLE_LABELS[kind],
            "backup": backup, "models": len(models), "notes": result.get("notes", []),
            "scan": found, **merge}
