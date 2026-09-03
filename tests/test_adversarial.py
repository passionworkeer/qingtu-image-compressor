import errno
import csv
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


def test_macos_appledouble_jpg_is_metadata_not_a_broken_photo(tmp_path):
    source = tmp_path / "外接硬盘照片"
    real = image(source / "Lab Fitting0139.jpg")
    real_dot_name = image(source / "._真实照片.jpg")
    sidecar = source / "._Lab Fitting0139.jpg"
    sidecar.write_bytes(b"\x00\x05\x16\x07" + b"metadata" * 512)
    original = {path: path.read_bytes() for path in (real, real_dot_name, sidecar)}

    result = run_batch(source)

    assert result.errors == result.skipped == 0
    assert result.unchanged == 2 and result.other == 1
    assert (result.output / real.name).is_file()
    assert (result.output / real_dot_name.name).is_file()
    assert not (result.output / sidecar.name).exists()
    assert all(path.read_bytes() == data for path, data in original.items())
    with result.report.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    metadata = next(row for row in rows if row["原文件"] == sidecar.name)
    assert metadata["状态"] == "macOS 元数据已跳过"
    assert metadata["输出文件"] == ""


def test_custom_output_parent_keeps_result_off_source_volume(tmp_path):
    external_drive = tmp_path / "外接盘" / "本次拍摄"
    local_export = tmp_path / "本机磁盘" / "导出位置"
    local_export.mkdir(parents=True)
    photo = image(external_drive / "第一组" / "成片.jpg")
    original = photo.read_bytes()

    result = run_batch(external_drive, output_parent=local_export)

    assert result.output.parent == local_export
    assert result.output.name == "本次拍摄_已压缩"
    assert (result.output / "第一组" / "成片.jpg").read_bytes() == original
    assert photo.read_bytes() == original


def test_custom_output_parent_must_be_an_existing_directory(tmp_path):
    source = image(tmp_path / "照片.jpg")
    with pytest.raises(ValueError, match="导出位置"):
        run_batch(source, output_parent=tmp_path / "不存在")
    file_target = tmp_path / "不是目录.txt"
    file_target.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="导出位置"):
        run_batch(source, output_parent=file_target)


@pytest.mark.parametrize("relative", [Path("."), Path("导出"), Path("导出") / "更深"])
def test_folder_output_parent_cannot_be_inside_source(tmp_path, relative):
    source = tmp_path / "整场拍摄"
    image(source / "机位1" / "成片.jpg")
    destination = source / relative
    destination.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError, match="源文件夹内部"):
        run_batch(source, output_parent=destination)

    assert not list(destination.glob("整场拍摄_已压缩*"))


def test_known_external_drive_system_folders_are_not_descended(tmp_path, monkeypatch):
    source = tmp_path / "外接硬盘"
    image(source / "客户照片" / "成片.jpg")
    system_folder = source / ".Spotlight-V100"
    image(system_folder / "索引伪装.jpg")
    original_scandir = compressor.os.scandir

    def fail_if_system_folder(path):
        if Path(path).name == ".Spotlight-V100":
            raise AssertionError("系统目录不应被读取")
        return original_scandir(path)

    monkeypatch.setattr(compressor.os, "scandir", fail_if_system_folder)
    result = run_batch(source)

    assert result.errors == result.skipped == 0
    assert result.unchanged == 1
    assert result.other == 1
    assert not (result.output / ".Spotlight-V100").exists()
    assert "系统目录已跳过" in result.report.read_text(encoding="utf-8-sig")


def test_known_operating_system_files_are_ignored_without_decoding(tmp_path, monkeypatch):
    source = tmp_path / "相机素材"
    image(source / "成片.jpg")
    metadata = source / ".DS_Store"
    metadata.write_bytes(b"not an image")
    original_open = compressor.Image.open

    def reject_metadata(path, *args, **kwargs):
        if Path(path).name == ".DS_Store":
            raise AssertionError("系统文件不应交给图片解码器")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(compressor.Image, "open", reject_metadata)
    result = run_batch(source)

    assert result.errors == result.skipped == 0
    assert result.unchanged == result.other == 1
    assert not (result.output / metadata.name).exists()
    assert "系统文件已跳过" in result.report.read_text(encoding="utf-8-sig")


def test_decompression_bomb_is_reported_and_not_copied(tmp_path, monkeypatch):
    source = tmp_path / "异常像素"
    safe = source / "正常.jpg"
    safe.parent.mkdir(parents=True)
    Image.new("RGB", (20, 20), "green").save(safe)
    bomb = source / "超大像素.jpg"
    Image.new("RGB", (42, 38), "red").save(bomb)
    monkeypatch.setattr(compressor, "MAX_IMAGE_PIXELS", 700)

    result = run_batch(source)

    assert result.errors == 1 and result.unchanged == 1
    assert (result.output / safe.name).exists()
    assert not (result.output / bomb.name).exists()
    report = result.report.read_text(encoding="utf-8-sig")
    assert "超过安全上限" in report
    assert "异常文件已跳过" in report


def test_later_multipage_frame_also_obeys_pixel_limit(tmp_path, monkeypatch):
    source = tmp_path / "多页像素上限"
    source.mkdir()
    photo = source / "第二页过大.tiff"
    first = Image.new("RGB", (20, 20), "green")
    second = Image.new("RGB", (42, 38), "red")
    first.save(photo, save_all=True, append_images=[second])
    monkeypatch.setattr(compressor, "MAX_IMAGE_PIXELS", 700)

    result = run_batch(source)

    assert result.errors == 1 and result.preserved == 0
    assert not (result.output / photo.name).exists()
    assert "超过安全上限" in result.report.read_text(encoding="utf-8-sig")


def test_truncated_image_is_not_left_in_results(tmp_path):
    source = tmp_path / "截断文件"
    image(source / "正常.jpg")
    broken = source / "传输中断.jpg"
    Image.effect_noise((800, 600), 70).convert("RGB").save(broken, quality=95)
    broken.write_bytes(broken.read_bytes()[:1000])

    result = run_batch(source)

    assert result.errors == 1 and result.unchanged == 1
    assert not (result.output / broken.name).exists()
    assert "异常文件已跳过" in result.report.read_text(encoding="utf-8-sig")


def test_truncated_later_animation_frame_is_not_preserved(tmp_path):
    source = tmp_path / "损坏动图"
    source.mkdir()
    first = Image.effect_noise((600, 500), 70).convert("RGB")
    second = Image.new("RGB", first.size, "blue")
    broken = source / "第二帧不完整.gif"
    first.save(broken, save_all=True, append_images=[second])
    broken.write_bytes(broken.read_bytes()[:-20])

    with Image.open(broken) as opened:
        assert opened.n_frames == 2
        with pytest.raises(OSError, match="truncated"):
            opened.seek(1)
            opened.load()

    result = run_batch(source)

    assert result.errors == 1 and result.preserved == 0
    assert not (result.output / broken.name).exists()
    assert "异常文件已跳过" in result.report.read_text(encoding="utf-8-sig")


def test_invalid_icc_metadata_does_not_discard_decodable_photo(tmp_path):
    source = tmp_path / "坏元数据"
    source.mkdir()
    photo = source / "像素正常.jpg"
    Image.effect_noise((1200, 900), 80).convert("RGB").save(
        photo, quality=98, icc_profile=b"bad-profile")
    assert photo.stat().st_size > 100_000

    result = run_batch(source, target_bytes=100_000)

    assert result.errors == 0 and result.compressed == 1
    output = result.output / photo.name
    assert output.stat().st_size <= 100_000
    with Image.open(output) as opened:
        opened.load()
        assert "icc_profile" not in opened.info
    assert "无效 ICC 色彩配置已移除" in result.report.read_text(encoding="utf-8-sig")


def test_invalid_icc_is_removed_on_png_lossless_fast_path(tmp_path):
    source = tmp_path / "PNG坏元数据"
    source.mkdir()
    photo = source / "像素正常.png"
    Image.new("RGB", (1200, 900), "#2478a8").save(
        photo, compress_level=0, icc_profile=b"not-an-icc")
    assert photo.stat().st_size > 100_000

    result = run_batch(source, target_bytes=100_000)

    assert result.errors == 0 and result.compressed == 1
    output = result.output / photo.name
    assert output.stat().st_size <= 100_000
    with Image.open(output) as opened:
        opened.load()
        assert "icc_profile" not in opened.info
    assert "无效 ICC 色彩配置已移除" in result.report.read_text(encoding="utf-8-sig")


def test_source_changed_after_validation_is_removed_from_results(tmp_path, monkeypatch):
    source = tmp_path / "仍在传输"
    photo = image(source / "尚未复制完成.jpg")
    original_write = compressor.write_file
    changed = False

    def replace_source_before_copy(destination, cancel, *, data=None, source=None):
        nonlocal changed
        if source is not None and not changed:
            changed = True
            Path(source).write_bytes(b"new incomplete payload")
        return original_write(destination, cancel, data=data, source=source)

    monkeypatch.setattr(compressor, "write_file", replace_source_before_copy)
    result = run_batch(source)

    assert result.errors == 1 and result.unchanged == 0
    assert not (result.output / photo.name).exists()
    assert "源文件在处理期间发生变化" in result.report.read_text(encoding="utf-8-sig")


def test_camera_batch_with_120_photos_and_appledouble_sidecars(tmp_path):
    source = tmp_path / "外接盘" / "整场拍摄"
    export_parent = tmp_path / "本机导出"
    export_parent.mkdir()
    originals = {}
    for index in range(120):
        folder = source / f"机位{index % 4 + 1}"
        photo = image(folder / f"成片{index:04}.jpg")
        sidecar = folder / f"._成片{index:04}.jpg"
        sidecar.write_bytes(b"\x00\x05\x16\x07" + index.to_bytes(4, "big") + b"metadata")
        originals[photo] = photo.read_bytes()
        originals[sidecar] = sidecar.read_bytes()

    result = run_batch(source, output_parent=export_parent)

    assert result.total == result.processed == 240
    assert result.unchanged == result.other == 120
    assert result.errors == result.skipped == result.preserved == 0
    assert len(list(result.output.rglob("*.jpg"))) == 120
    assert all(path.read_bytes() == data for path, data in originals.items())


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


def test_external_drive_disconnect_stops_after_first_io_error(tmp_path, monkeypatch):
    source = tmp_path / "已断开的外接盘"
    for index in range(8):
        image(source / f"{index}.jpg")

    def disconnected(*args, **kwargs):
        raise OSError(errno.EIO, "external disk disconnected")

    monkeypatch.setattr(compressor, "process_file", disconnected)
    result = run_batch(source)

    assert result.total == 8
    assert result.processed == result.errors == 1
    assert result.fatal_error.startswith("存储设备已断开或读写失败")
    assert "副本未完整" in result.report.read_text(encoding="utf-8-sig")


def test_output_destination_existing_file_is_never_overwritten(tmp_path):
    target = tmp_path / "existing.jpg"
    target.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        compressor.write_file(target, threading.Event(), data=b"replacement")
    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob("*.part"))


def test_posix_publish_falls_back_when_hard_links_are_unsupported(tmp_path, monkeypatch):
    target = tmp_path / "result.jpg"
    monkeypatch.setattr(compressor.os, "link", lambda *args: (_ for _ in ()).throw(OSError(errno.EPERM, "no links")))
    staged = tmp_path / ".stage.part"
    staged.write_bytes(b"complete")
    compressor.publish_staged(staged, target, threading.Event(), platform_name="posix")
    assert target.read_bytes() == b"complete"
    assert not list(tmp_path.glob("*.part"))


def test_direct_symlink_input_is_rejected_when_platform_supports_it(tmp_path):
    source = image(tmp_path / "source.jpg")
    link = tmp_path / "link.jpg"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="链接"):
        run_batch(link)


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
