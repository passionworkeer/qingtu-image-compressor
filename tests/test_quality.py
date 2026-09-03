import csv
import io
import random
import struct

from PIL import Image, ImageChops, ImageCms, ImageStat, JpegImagePlugin, PngImagePlugin

from compressor import encode_image, run_batch


def test_jpeg_keeps_coloured_fine_lines():
    image = Image.new("RGB", (256, 128))
    # Equal-luminance red/green stripes reveal chroma subsampling damage.
    image.putdata([(255, 0, 0) if x % 4 < 2 else (0, 130, 0)
                   for y in range(128) for x in range(256)])
    encoded = encode_image(image, "JPEG", 90, None)
    with Image.open(io.BytesIO(encoded)) as result:
        assert JpegImagePlugin.get_sampling(result) == 0
        assert max(ImageStat.Stat(ImageChops.difference(image, result)).mean) < 10


def test_palette_png_tries_lossless_before_resizing(tmp_path):
    picture = tmp_path / "palette.png"
    rng = random.Random(90)
    image = Image.new("P", (700, 500))
    image.putpalette([channel for i in range(256) for channel in (i, 255-i, i // 2)])
    image.putdata([rng.randrange(64) for _ in range(700 * 500)])
    image.save(picture, compress_level=0, transparency=0)
    lossless = io.BytesIO()
    image.save(lossless, format="PNG", optimize=True, transparency=0)
    target = len(lossless.getvalue())
    assert target < picture.stat().st_size
    result = run_batch(picture, target)
    assert result.errors == 0
    with Image.open(result.output / "palette.png") as output:
        assert output.size == image.size
        with Image.open(picture) as original:
            assert output.convert("RGBA").tobytes() == original.convert("RGBA").tobytes()


def test_high_bit_depth_is_preserved_instead_of_clipped(tmp_path):
    picture = tmp_path / "16bit.tif"
    image = Image.new("I", (512, 256))
    image.putdata([x * 128 for y in range(256) for x in range(512)])
    image.convert("I;16").save(picture)
    original = picture.read_bytes()
    result = run_batch(picture, 30_000)
    assert result.errors == 0
    assert result.preserved == 1
    assert (result.output / picture.name).read_bytes() == original
    rows = list(csv.DictReader(result.report.open(encoding="utf-8-sig")))
    assert "位深" in rows[0]["说明"]


def test_png_gamma_is_kept_when_resizing(tmp_path):
    picture = tmp_path / "gamma.png"
    image = Image.effect_noise((512, 512), 80).convert("RGB")
    chunks = PngImagePlugin.PngInfo()
    chunks.add(b"gAMA", struct.pack(">I", 100000))
    image.save(picture, pnginfo=chunks)
    result = run_batch(picture, 50_000)
    assert result.errors == 0
    with Image.open(result.output / picture.name) as output:
        assert output.info["gamma"] == 1.0


def test_jpeg_quality_floor_survives_tight_byte_budget(tmp_path):
    picture = tmp_path / "photo.tif"
    Image.effect_noise((900, 700), 80).convert("RGB").save(picture)
    reference = io.BytesIO()
    Image.new("RGB", (8, 8)).save(reference, format="JPEG", quality=82)
    with Image.open(io.BytesIO(reference.getvalue())) as minimum:
        floor = minimum.quantization[0]
    result = run_batch(picture, 50_000)
    with Image.open(result.output / "photo.jpg") as output:
        assert all(a <= b for a, b in zip(output.quantization[0], floor))
        assert output.width < 900
        assert (result.output / "photo.jpg").stat().st_size <= 50_000


def test_webp_lossless_optimization_preserves_pixels(tmp_path):
    picture = tmp_path / "lossless.webp"
    image = Image.new("RGB", (256, 128))
    image.putdata([(255, 0, 0) if x % 4 < 2 else (0, 130, 0)
                   for y in range(128) for x in range(256)])
    image.save(picture, lossless=True, xmp=b"a" * 30_000)
    result = run_batch(picture, 10_000)
    with Image.open(result.output / picture.name) as output:
        assert output.convert("RGB").tobytes() == image.tobytes()


def test_icc_rgb_transparent_colour_survives_resize(tmp_path):
    picture = tmp_path / "transparent.png"
    image = Image.frombytes("RGB", (180, 140), random.Random(8).randbytes(180 * 140 * 3))
    image.paste((255, 0, 0), (0, 0, 60, 60))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    image.save(picture, transparency=(255, 0, 0), icc_profile=profile)
    result = run_batch(picture, 10_000)
    assert result.errors == 0
    with Image.open(result.output / picture.name) as output:
        assert output.getextrema()[3] == (0, 255)
        assert output.getpixel((0, 0))[3] == 0


def test_noisy_444_jpeg_can_exceed_pillow_memory_buffer():
    image = Image.frombytes("RGB", (700, 500), random.Random(33).randbytes(700 * 500 * 3))
    data = encode_image(image, "JPEG", 82, None)
    with Image.open(io.BytesIO(data)) as output:
        output.load()
        assert output.size == image.size
        assert JpegImagePlugin.get_sampling(output) == 0
