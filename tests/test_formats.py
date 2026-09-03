import csv
import hashlib
import threading
from pathlib import Path

import pytest
from PIL import Image, ImageCms
from compressor import run_batch, Cancelled


@pytest.mark.parametrize("fmt,ext", [("JPEG", ".jpeg"), ("WEBP", ".webp"),
                                     ("HEIF", ".heic"), ("AVIF", ".avif"), ("TIFF", ".tif")])
def test_large_supported_formats(fmt, ext, tmp_path):
    source = tmp_path / fmt
    source.mkdir()
    im = Image.effect_noise((900, 750), 90).convert("RGB")
    im.save(source / ("test" + ext), format=fmt, quality=95)
    result = run_batch(source, target_bytes=60_000)
    assert result.errors == 0
    assert result.compressed == 1
    with result.report.open(encoding="utf-8-sig", newline="") as handle:
        record = list(csv.DictReader(handle))[0]
    output = result.output / record["输出文件"]
    assert output.stat().st_size <= 60_000
    with Image.open(output) as read:
        read.load()
        assert read.width > 150


def test_icc_profile_is_valid_after_compression(tmp_path):
    source = tmp_path / "色彩"
    source.mkdir()
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    im = Image.effect_noise((900, 700), 80).convert("RGB")
    im.save(source / "色彩.jpg", quality=95, icc_profile=profile)
    result = run_batch(source, target_bytes=60_000)
    assert result.errors == 0
    with Image.open(result.output / "色彩.jpg") as read:
        assert read.info.get("icc_profile")
        assert read.mode == "RGB"


def test_csv_report_does_not_overwrite_input_and_escapes_formulas(tmp_path):
    source = tmp_path / "报告"
    source.mkdir()
    (source / "_压缩报告.csv").write_bytes(b"original report")
    Image.new("RGB", (30, 20), "red").save(source / "=1+1.jpg")
    result = run_batch(source)
    assert result.report.name != "_压缩报告.csv"
    assert (source / "_压缩报告.csv").read_bytes() == b"original report"
    assert not (result.output / "_压缩报告.csv").exists()
    assert result.other == 1
    with result.report.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    assert any(r["原文件"] == "'=1+1.jpg" for r in records)


def test_cancel_before_scan_creates_nothing(tmp_path):
    source = tmp_path / "扫描取消"
    source.mkdir()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        run_batch(source, cancel=cancel)
    assert list(tmp_path.iterdir()) == [source]


def test_empty_folder_creates_readable_report(tmp_path):
    source = tmp_path / "空目录"
    source.mkdir()
    result = run_batch(source)
    assert result.total == 0
    assert result.report.is_file()
    assert result.errors == 0
