"""Run after a Mac build to prove the bundle includes codecs and starts its GUI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from PIL import Image

root = Path(__file__).resolve().parent
app = root / "dist-macos" / "轻图图片压缩.app" / "Contents" / "MacOS" / "轻图图片压缩"
with tempfile.TemporaryDirectory() as folder:
    source = Path(folder) / "测试图"
    source.mkdir()
    picture = source / "深层" / "大图.jpg"
    picture.parent.mkdir()
    Image.effect_noise((2400, 1800), 85).convert("RGB").save(picture, quality=100)
    before = hashlib.sha256(picture.read_bytes()).hexdigest()
    result_path = Path(folder) / "result.json"
    run = subprocess.run([str(app), "--batch", str(source), "--target-mb", "1",
                          "--result-json", str(result_path)], timeout=180)
    assert run.returncode == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["processed"] == result["total"] == 1 and result["errors"] == 0
    assert hashlib.sha256(picture.read_bytes()).hexdigest() == before
    output = next((Path(result["output"]) / "深层").glob("*.jpg"))
    assert output.stat().st_size <= 1_000_000
    with Image.open(output) as read:
        read.load()
process = subprocess.Popen([str(app)])
time.sleep(6)
assert process.poll() is None, "Mac GUI exited during startup"
process.terminate()
process.wait(timeout=20)
print("MAC_BUNDLE_SMOKE_OK", os.uname().machine)
