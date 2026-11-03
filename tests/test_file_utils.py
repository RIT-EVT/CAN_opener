#--------------------#
# test_file_utils.py
# tests for data folder setup and first-run default copies
#--------------------#
from utils.file_utils import atomic_write_text, copy_default_if_missing, ensure_directories


def test_atomic_write_text(tmp_path):
    target = tmp_path / "out.yaml"
    atomic_write_text(target, "hello: world\n")
    assert target.read_text() == "hello: world\n"
    assert not target.with_suffix(target.suffix + ".tmp").exists()


def test_copy_default_if_missing(tmp_path):
    src = tmp_path / "src.yaml"
    src.write_text("a: 1\n")
    dst = tmp_path / "sub" / "dst.yaml"

    assert copy_default_if_missing(src, dst) is True
    assert dst.read_text() == "a: 1\n"

    dst.write_text("a: 2\n")  # simulate a user edit
    assert copy_default_if_missing(src, dst) is False
    assert dst.read_text() == "a: 2\n"  # never overwritten


def test_ensure_directories(tmp_path):
    ensure_directories(tmp_path)
    assert (tmp_path / "config" / "platforms").is_dir()
    assert (tmp_path / "config" / "themes").is_dir()
    assert (tmp_path / "dbc_store").is_dir()
    assert (tmp_path / "logs_cache").is_dir()
    # versions/ lives beside the data root, not inside it
    assert not (tmp_path / "versions").exists()
