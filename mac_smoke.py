"""Run after a Mac build to prove the bundle includes codecs and starts its GUI."""
import hashlib
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

root = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as folder:
    archive = root / "dist-macos" / f"轻图图片压缩-macOS-{os.uname().machine}.zip"
    unpacked = Path(folder) / "解压校验"
    subprocess.run(["ditto", "-x", "-k", str(archive), str(unpacked)], check=True)
    bundle = unpacked / "轻图图片压缩.app"
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
    app = bundle / "Contents" / "MacOS" / "轻图图片压缩"
    source = Path(folder) / "测试图"
    source.mkdir()
    picture = source / "深层" / "大图.jpg"
    picture.parent.mkdir()
    Image.effect_noise((2400, 1800), 85).convert("RGB").save(picture, quality=100)
    before = hashlib.sha256(picture.read_bytes()).hexdigest()
    for fmt, suffix in (("HEIF", "heic"), ("WEBP", "webp"), ("AVIF", "avif"), ("PNG", "png")):
        with Image.effect_noise((1000, 800), 90).convert("RGB") as sample:
            sample.save(source / f"编码器.{suffix}", format=fmt, quality=100)
    result_path = Path(folder) / "result.json"
    run = subprocess.run([str(app), "--batch", str(source), "--target-mb", "0.1",
                          "--result-json", str(result_path)], timeout=180)
    assert run.returncode == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["processed"] == result["total"] == 5 and result["errors"] == 0
    assert hashlib.sha256(picture.read_bytes()).hexdigest() == before
    output = next((Path(result["output"]) / "深层").glob("*.jpg"))
    assert output.stat().st_size <= 100_000
    with Image.open(output) as read:
        read.load()
    with Path(result["report"]).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if not row["输出文件"]:
            continue
        output = Path(result["output"]) / row["输出文件"]
        assert row["状态"] == "已压缩"
        assert output.stat().st_size <= 100_000
        with Image.open(output) as read:
            read.load()
    # The single-image entry point must work from the extracted bundle too.
    single_json = Path(folder) / "single.json"
    subprocess.run([str(app), "--batch", str(picture), "--result-json", str(single_json)],
                   check=True, timeout=180)
    assert json.loads(single_json.read_text(encoding="utf-8"))["processed"] == 1
    process = subprocess.Popen([str(app)])
    try:
        time.sleep(6)
        assert process.poll() is None, "Mac GUI exited during startup"
    finally:
        process.terminate()
        process.wait(timeout=20)
print("MAC_BUNDLE_SMOKE_OK", os.uname().machine)
