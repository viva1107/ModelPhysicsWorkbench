import io
import zipfile

import pytest

from retroport.workbench import deps


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return stream.getvalue()


def test_unpack_removes_github_top_folder(tmp_path):
    data = archive({"repo-sha/tools/physics_table.py": b"# tool", "repo-sha/README.md": b"readme"})
    deps.unpack(data, str(tmp_path / "out"))
    assert (tmp_path / "out" / "tools" / "physics_table.py").read_bytes() == b"# tool"


def test_unpack_rejects_path_traversal(tmp_path):
    data = archive({"repo-sha/../../outside.txt": b"bad"})
    with pytest.raises(RuntimeError, match="越界"):
        deps.unpack(data, str(tmp_path / "out"))


def test_fetch_checks_pinned_entry(tmp_path):
    data = archive({"repo-sha/tools/physics_table.py": b"# tool"})

    def get(url, dest):
        with open(dest, "wb") as fh:
            fh.write(data)

    path = deps.fetch(str(tmp_path), "equip-plus", say=lambda message: None, get=get)
    assert open(path, "rb").read() == b"# tool"
    assert deps.have(str(tmp_path), "equip-plus")
