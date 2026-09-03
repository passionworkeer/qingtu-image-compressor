import errno
import hashlib
import threading
from types import SimpleNamespace
from pathlib import Path

import pytest
from PIL import Image
import compressor
from compressor import run_batch


def image(path, fmt="JPEG"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (42, 38), "#178c76").save(path, format=fmt)
    return path


def test_single_image_creates_sibling_result_folder(tmp_path):
    source = image(tmp_path / "单张 图片.jpg")
    original = source.read_bytes()
    result = run_batch(source)
    assert result.total == 1 and result.errors == 0
    assert result.output.parent == source.parent
    assert (result.output / source.name).read_bytes() == original
    assert source.read_bytes() == original


def test_multiple_images_same_parent_deduplicated(tmp_path):
    a, b = image(tmp_path / "a.jpg"), image(tmp_path / "b.jpg")
    result = run_batch([a, b, a])
    assert result.total == 2
    assert result.unchanged == 2
    assert len(list(result.output.glob("*.jpg"))) == 2


def test_28_levels_and_siblings_cover_every_image(tmp_path):
    source = tmp_path / "深目录"
    current = source
    expected = {}
    for depth in range(28):
        current /= "d"
        for branch in ("a", "b"):
            path = image(current / branch / "图.jpg")
            expected[path.relative_to(source)] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = run_batch(source)
    assert result.total == result.processed == result.unchanged == 56
    assert result.errors == result.skipped == 0
    for relative, digest in expected.items():
        assert hashlib.sha256((result.output / relative).read_bytes()).hexdigest() == digest


def test_recognizes_images_without_extension_and_with_wrong_extension(tmp_path):
    source = tmp_path / "无后缀"
    image(source / "扫描件", "PNG")
    image(source / "误命名.dat", "JPEG")
    result = run_batch(source)
    assert result.unchanged == 2
    assert result.other == 0
    assert (result.output / "扫描件.png").is_file()
    assert (result.output / "误命名.jpg").is_file()


def test_scan_failure_is_visible_and_siblings_still_processed(tmp_path, monkeypatch):
    source = tmp_path / "部分无权限"
    image(source / "禁止" / "图.jpg")
    image(source / "正常" / "图.jpg")
    original = compressor.os.scandir
    def denied(path):
        if Path(path).name == "禁止":
            raise PermissionError("模拟权限拒绝")
        return original(path)
    monkeypatch.setattr(compressor.os, "scandir", denied)
    result = run_batch(source)
    assert result.errors == 1
    assert result.unchanged == 1
    assert "模拟权限拒绝" in result.report.read_text(encoding="utf-8-sig")


def test_disk_full_stops_batch_with_incomplete_status(tmp_path, monkeypatch):
    source = tmp_path / "磁盘满"
    for i in range(5):
        image(source / f"{i}.jpg")
    def disk_full(*args, **kwargs):
        raise OSError(errno.ENOSPC, "磁盘空间不足")
    monkeypatch.setattr(compressor, "write_file", disk_full)
    result = run_batch(source)
    assert result.fatal_error
    assert result.processed < result.total
    assert result.errors >= 1
    assert "未完整" in result.report.read_text(encoding="utf-8-sig")


def test_output_destination_existing_file_is_never_overwritten(tmp_path):
    target = tmp_path / "existing.jpg"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        compressor.write_file(target, threading.Event(), data=b"replacement")
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.part"))


def test_rejects_mixed_folder_and_file_input(tmp_path):
    folder = tmp_path / "目录"
    folder.mkdir()
    source = image(tmp_path / "a.jpg")
    with pytest.raises(ValueError):
        run_batch([folder, source])


def test_cloud_reparse_is_allowed_but_name_surrogate_is_skipped():
    entry = SimpleNamespace(is_symlink=lambda: False)
    cloud = SimpleNamespace(st_reparse_tag=0x9000001A)
    symlink = SimpleNamespace(st_reparse_tag=0xA000000C)
    junction = SimpleNamespace(st_reparse_tag=0xA0000003)
    assert not compressor.is_link_like(entry, cloud)
    assert compressor.is_link_like(entry, symlink)
    assert compressor.is_link_like(entry, junction)


def test_long_converted_name_is_shortened_and_readable(tmp_path):
    source = tmp_path / "长名称"
    path = source / (("a" * 120) + ".bmp")
    path.parent.mkdir()
    Image.effect_noise((700, 600), 90).convert("RGB").save(path)
    result = run_batch(source, target_bytes=30_000)
    records = list(result.output.glob("*.jpg"))
    assert result.errors == 0 and len(records) == 1
    assert len(records[0].name.encode("utf-8")) <= 200
    with Image.open(records[0]) as read:
        read.load()
    generated = compressor.shortened_name("图" * 200, ".jpg", "_压缩")
    assert len(generated.encode("utf-8")) <= 200
    assert generated.endswith("_压缩.jpg")
