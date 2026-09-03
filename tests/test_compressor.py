import csv
import hashlib
import threading
from pathlib import Path

import pytest
from PIL import Image

from compressor import run_batch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def picture(path, size=(100, 70), color="red", **save):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, **save)
    return path


def test_recurses_preserves_originals_and_skips_other_files(tmp_path):
    source = tmp_path / "中文 资料"
    img = picture(source / "客户 一" / "照片.JPG")
    (source / "空文件夹").mkdir()
    note = source / "说明.txt"
    note.write_text("原样保留", encoding="utf-8")
    before = {p.relative_to(source): digest(p) for p in source.rglob("*") if p.is_file()}
    result = run_batch(source)
    assert result.output.parent == source.parent
    assert result.output != source
    assert (result.output / "空文件夹").is_dir()
    assert result.cancelled is False
    assert result.errors == 0
    for rel, sha in before.items():
        assert digest(source / rel) == sha
    assert digest(result.output / img.relative_to(source)) == digest(img)
    assert not (result.output / note.name).exists()
    assert result.other == 1
    assert result.report.is_file()
    again = run_batch(source)
    assert again.output != result.output


def test_nested_non_images_are_not_written_or_counted_as_savings(tmp_path):
    source = tmp_path / "混合素材"
    nested = source / "活动" / "第二天" / "摄影组"
    nested.mkdir(parents=True)
    photo = picture(nested / "没有后缀", format="JPEG")
    wrong_suffix = picture(nested / "真实图片.mp4", format="PNG")
    non_images = [nested / name for name in ("视频.mov", "说明.pdf", "清单.xlsx", "无后缀文档")]
    for path in non_images:
        path.write_bytes(b"not an image" * 1000)
    before = {p: digest(p) for p in (photo, wrong_suffix, *non_images)}
    result = run_batch(source)
    assert result.unchanged == 2
    assert result.other == 4
    assert result.errors == result.skipped == result.saved_bytes == 0
    assert result.output_bytes == photo.stat().st_size + wrong_suffix.stat().st_size
    for path in non_images:
        assert not (result.output / path.relative_to(source)).exists()
    with result.report.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ignored = [row for row in rows if row["状态"] == "非图片已跳过"]
    assert len(ignored) == 4
    assert all(row["输出文件"] == "" and row["新大小(字节)"] == "0" for row in ignored)
    for row in rows:
        if row["状态"] == "已达标":
            with Image.open(result.output / row["输出文件"]) as image:
                image.load()
    assert all(digest(path) == sha for path, sha in before.items())


def test_unidentified_unsupported_suffix_and_document_are_not_copied(tmp_path):
    source = tmp_path / "原始素材"
    source.mkdir()
    raw = source / "相机.CR3"
    raw.write_bytes(b"unsupported raw placeholder")
    fake_svg = source / "伪装.svg"
    fake_svg.write_text("<html>not an image</html>", encoding="utf-8")
    fake_psd = source / "伪装.psd"
    fake_psd.write_bytes(b"arbitrary bytes")
    note = source / "备注.txt"
    note.write_text("不复制", encoding="utf-8")
    result = run_batch(source)
    assert result.skipped == 3
    assert result.other == 1
    assert result.preserved == result.errors == 0
    assert all(not (result.output / path.name).exists() for path in (raw, fake_svg, fake_psd, note))
    assert "无法确认是有效图片" in result.report.read_text(encoding="utf-8-sig")


def test_large_20mb_image_meets_limit_and_remains_readable(tmp_path):
    source = tmp_path / "大图"
    source.mkdir()
    image_path = source / "大照片.bmp"
    noise = Image.effect_noise((3000, 2600), 80).convert("RGB")
    noise.save(image_path)
    original_hash = digest(image_path)
    assert image_path.stat().st_size > 20_000_000
    result = run_batch(source)
    compressed = result.output / "大照片.jpg"
    assert 100_000 < compressed.stat().st_size <= 1_000_000
    with Image.open(compressed) as im:
        im.load()
        assert im.width > 800
        assert abs(im.width / im.height - 3000 / 2600) < 0.003
    assert digest(image_path) == original_hash
    assert result.compressed == 1


def test_converted_filename_never_overwrites_a_source_file_or_directory(tmp_path):
    source = tmp_path / "同名"
    source.mkdir()
    Image.effect_noise((700, 600), 90).convert("RGB").save(source / "a.bmp")
    jpg = picture(source / "a.jpg")
    (source / "a_压缩.jpg").mkdir()
    result = run_batch(source, target_bytes=30_000)
    assert digest(result.output / "a.jpg") == digest(jpg)
    assert (result.output / "a_压缩.jpg").is_dir()
    other = list(result.output.glob("a_压缩*.jpg"))
    assert any(p.is_file() and p.stat().st_size <= 30_000 for p in other)


def test_transparency_is_preserved(tmp_path):
    source = tmp_path / "透明"
    source.mkdir()
    im = Image.effect_noise((900, 700), 70).convert("RGBA")
    im.putalpha(120)
    im.save(source / "透明.png")
    result = run_batch(source, target_bytes=80_000)
    output = result.output / "透明.png"
    assert output.stat().st_size <= 80_000
    with Image.open(output) as read:
        assert read.mode == "RGBA"
        assert read.getextrema()[3] == (120, 120)


def test_exif_orientation_applied_before_metadata_removed(tmp_path):
    source = tmp_path / "旋转"
    source.mkdir()
    im = Image.effect_noise((1000, 600), 70).convert("RGB")
    exif = Image.Exif()
    exif[274] = 6
    im.save(source / "竖图.jpg", quality=98, exif=exif)
    result = run_batch(source, target_bytes=80_000)
    with Image.open(result.output / "竖图.jpg") as read:
        assert read.height > read.width
        assert read.getexif().get(274, 1) == 1


def test_animation_and_multipage_preserved_with_explicit_warning(tmp_path):
    source = tmp_path / "动态"
    source.mkdir()
    first = Image.effect_noise((600, 500), 70).convert("RGB")
    second = Image.new("RGB", first.size, "blue")
    for ext in ("gif", "tiff"):
        first.save(source / ("多帧." + ext), save_all=True, append_images=[second])
    result = run_batch(source, target_bytes=20_000)
    assert result.preserved == 2
    assert result.compressed == 0
    for path in source.iterdir():
        assert digest(result.output / path.name) == digest(path)
        with Image.open(result.output / path.name) as read:
            assert read.n_frames == 2
    assert "多帧" in result.report.read_text(encoding="utf-8-sig")


def test_corrupt_image_does_not_abort_other_files(tmp_path):
    source = tmp_path / "坏图"
    good = picture(source / "正常.jpg")
    bad = source / "损坏.jpg"
    bad.write_bytes(b"this is not an image" * 3000)
    result = run_batch(source, target_bytes=20_000)
    assert result.errors == 1
    assert digest(result.output / good.name) == digest(good)
    assert not (result.output / bad.name).exists()
    report = result.report.read_text(encoding="utf-8-sig")
    assert "异常文件已跳过" in report
    assert "未复制到结果文件夹" in report


def test_cancellation_leaves_report_and_no_temporary_file(tmp_path):
    source = tmp_path / "取消"
    for index in range(5):
        picture(source / (str(index) + ".jpg"))
    stop = threading.Event()

    def update(event):
        if event["type"] == "file":
            stop.set()

    result = run_batch(source, cancel=stop, emit=update)
    assert result.cancelled
    assert result.processed == 1
    assert result.report.exists()
    assert not list(result.output.rglob("*.part"))


def test_invalid_source_does_not_create_output(tmp_path):
    with pytest.raises(ValueError):
        run_batch(tmp_path / "missing")
    with pytest.raises(ValueError):
        run_batch(tmp_path, target_bytes=0)
