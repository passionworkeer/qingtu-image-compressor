import errno
import os
import subprocess
from pathlib import Path

import pytest
from PIL import Image

import compressor


def test_unicode_conversion_reserves_decomposed_original_name(tmp_path):
    folder = tmp_path / "unicode"
    folder.mkdir()
    stem = "cafe\u0301"
    Image.new("RGB", (300, 300), "red").save(folder / (stem + ".bmp"))
    Image.new("RGB", (20, 20), "blue").save(folder / (stem + ".jpg"))
    original = (folder / (stem + ".jpg")).read_bytes()
    result = compressor.run_batch(folder, 30_000)
    assert result.errors == 0
    assert (result.output / (stem + ".jpg")).read_bytes() == original
    assert (result.output / (stem + "_压缩.jpg")).exists()


def test_added_suffix_shortens_even_without_collision():
    name = compressor.reserve_name("a" * 253 + ".jpg", set())
    assert len(name.encode("utf-8")) <= 200
    assert name.endswith(".jpg")


def test_disk_full_during_empty_directory_creation_stops_batch(tmp_path, monkeypatch):
    folder = tmp_path / "folders"
    folder.mkdir()
    for i in range(4):
        (folder / str(i)).mkdir()
    original = Path.mkdir
    attempts = []

    def mkdir(path, *args, **kwargs):
        if "folders_已压缩" in str(path.parent):
            attempts.append(path)
            raise OSError(errno.ENOSPC, "disk full")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    result = compressor.run_batch(folder)
    assert result.fatal_error
    assert len(attempts) == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows long path regression")
def test_legal_source_path_still_copies_when_output_crosses_max_path(tmp_path):
    folder = tmp_path / "source"
    folder.mkdir()
    nested = folder / ("a" * 100)
    nested.mkdir()
    stem_length = 258 - len(str(nested)) - len("\\.jpg")
    if stem_length < 1:
        pytest.skip("test temporary directory is already too long")
    source = nested / ("b" * stem_length + ".jpg")
    Image.new("RGB", (10, 10), "red").save(source)
    result = compressor.run_batch(folder)
    assert result.errors == 0
    destination = result.output / source.relative_to(folder)
    assert Path("\\\\?\\" + str(destination)).read_bytes() == source.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_direct_junction_is_rejected_before_resolve(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    junction = tmp_path / "junction"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(actual)],
                   check=True, capture_output=True)
    try:
        with pytest.raises(ValueError, match="链接"):
            compressor.run_batch(junction)
        assert not (tmp_path / "actual_已压缩").exists()
    finally:
        os.rmdir(junction)


@pytest.mark.skipif(os.name == "nt", reason="POSIX scan-to-open symlink regression")
def test_file_replaced_by_symlink_after_scan_is_not_followed(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.jpg"
    Image.new("RGB", (10, 10), "red").save(outside)
    selected = source / "selected.jpg"
    Image.new("RGB", (10, 10), "blue").save(selected)
    original_scan = compressor.scan_folder

    def replace_after_scan(*args, **kwargs):
        result = original_scan(*args, **kwargs)
        selected.unlink()
        selected.symlink_to(outside)
        return result

    monkeypatch.setattr(compressor, "scan_folder", replace_after_scan)
    result = compressor.run_batch(source)

    assert result.errors == 1 and result.unchanged == 0
    assert not (result.output / selected.name).exists()
    assert "扫描后变成了链接" in result.report.read_text(encoding="utf-8-sig")
