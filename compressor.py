"""Local batch compression; source files are opened read-only."""
from __future__ import annotations

import csv
import errno
import hashlib
import io
import math
import os
import shutil
import stat
import tempfile
import threading
import unicodedata
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".bmp",
                    ".dib", ".tif", ".tiff", ".gif", ".heic", ".heif", ".avif"}
UNSUPPORTED_IMAGES = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf",
                      ".rw2", ".psd", ".svg", ".ico", ".jxl", ".jp2", ".eps"}
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "DIB", "TIFF", "GIF", "HEIF", "AVIF"}
VALID_SUFFIXES = {
    "JPEG": {".jpg", ".jpeg", ".jpe", ".jfif"}, "PNG": {".png"},
    "WEBP": {".webp"}, "BMP": {".bmp"}, "DIB": {".dib"},
    "TIFF": {".tif", ".tiff"}, "GIF": {".gif"},
    "HEIF": {".heic", ".heif"}, "AVIF": {".avif"},
}
CANONICAL_SUFFIX = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp",
                    "DIB": ".dib", "TIFF": ".tif", "GIF": ".gif", "HEIF": ".heic",
                    "AVIF": ".avif"}
FATAL_IO = {errno.ENOSPC, getattr(errno, "EDQUOT", 122), errno.EROFS}


class Cancelled(Exception):
    pass


@dataclass
class BatchResult:
    output: Path
    report: Path
    total: int = 0
    processed: int = 0
    compressed: int = 0
    unchanged: int = 0
    other: int = 0
    preserved: int = 0
    errors: int = 0
    skipped: int = 0
    input_bytes: int = 0
    output_bytes: int = 0
    saved_bytes: int = 0
    cancelled: bool = False
    fatal_error: str = ""


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled()


def is_link_like(entry, info) -> bool:
    """Skip path redirects, while allowing ordinary hydrated cloud files."""
    if entry.is_symlink():
        return True
    tag = getattr(info, "st_reparse_tag", 0)
    return bool(tag & 0x20000000)  # IO_REPARSE_TAG_NAME_SURROGATE: symlink/junction/mount.


def scan_folder(source: Path, cancel: threading.Event, emit: Callable):
    """Iterative walk: never follow symlinks or Windows junctions."""
    pending = [source]
    folders = []
    items = []
    reserved: dict[Path, set[str]] = {}
    while pending:
        check_cancel(cancel)
        folder = pending.pop()
        relative = folder.relative_to(source)
        try:
            with os.scandir(folder) as iterator:
                entries = sorted(iterator, key=lambda e: e.name.casefold())
            reserved[relative] = {e.name.casefold() for e in entries}
        except OSError as exc:
            items.append((relative, "error", str(exc)))
            continue
        for entry in entries:
            check_cancel(cancel)
            rel = relative / entry.name
            try:
                info = entry.stat(follow_symlinks=False)
                if is_link_like(entry, info):
                    items.append((rel, "skip", "链接或联接点未跟随，请单独选择实际文件夹"))
                elif entry.is_dir(follow_symlinks=False):
                    folders.append(rel)
                    pending.append(source / rel)
                elif entry.is_file(follow_symlinks=False):
                    items.append((rel, "file", ""))
                else:
                    items.append((rel, "skip", "不是普通文件"))
            except OSError as exc:
                items.append((rel, "error", str(exc)))
        emit({"type": "scan", "found": len(items)})
    return folders, items, reserved


def name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def shortened_name(stem: str, suffix: str = "", marker: str = "") -> str:
    """Keep generated names below conservative Windows/APFS component limits."""
    proposed = stem + marker + suffix
    if len(proposed.encode("utf-8")) <= 200:
        return proposed
    digest = hashlib.sha256(stem.encode("utf-8")).hexdigest()[:8]
    budget = 185 - len((marker + suffix).encode("utf-8"))
    raw = stem.encode("utf-8")[:max(1, budget)]
    while True:
        try:
            cut = raw.decode("utf-8")
            break
        except UnicodeDecodeError:
            raw = raw[:-1]
    return f"{cut}_{digest}{marker}{suffix}"


def new_output(parent: Path, source_name: str) -> Path:
    base = shortened_name(source_name, marker="_已压缩")
    index = 1
    while True:
        name = base if index == 1 else f"{base} ({index})"
        output = parent / name
        try:
            output.mkdir()
            return output
        except FileExistsError:
            index += 1


def reserve_name(name: str, occupied: set[str]) -> str:
    path = Path(name)
    candidate = name
    index = 1
    while name_key(candidate) in occupied:
        tail = "_压缩" if index == 1 else f"_压缩{index}"
        candidate = shortened_name(path.stem, path.suffix, tail)
        index += 1
    occupied.add(name_key(candidate))
    return candidate


def write_file(destination: Path, cancel: threading.Event, *, data: bytes | None = None,
               source: Path | None = None) -> None:
    """Publish a complete file only. Windows rename refuses an existing target."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".img-", suffix=".part",
                                         delete=False) as out:
            temporary = Path(out.name)
            if data is not None:
                check_cancel(cancel)
                out.write(data)
            else:
                with source.open("rb") as inp:
                    while chunk := inp.read(1024 * 1024):
                        check_cancel(cancel)
                        out.write(chunk)
        check_cancel(cancel)
        if os.name == "nt":
            if destination.exists():
                raise FileExistsError(f"输出文件已存在：{destination.name}")
            os.rename(temporary, destination)
        else:
            # POSIX rename replaces an existing file. Hard-link publication is atomic and
            # fails with EEXIST, preserving a concurrent writer's data.
            os.link(temporary, destination)
            temporary.unlink()
        temporary = None
        if source:
            try:
                shutil.copystat(source, destination)
            except OSError:
                pass  # Contents are already safely published; timestamps are best effort.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_image(opened: Image.Image) -> tuple[Image.Image, bytes | None]:
    im = ImageOps.exif_transpose(opened)
    has_alpha = "A" in im.getbands() or "transparency" in im.info
    mode = "RGBA" if has_alpha else "RGB"
    profile = im.info.get("icc_profile")
    if profile:
        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
        # CMYK and LAB must be converted with their source profile before RGB conversion.
        if im.mode not in ("RGB", "RGBA", "CMYK", "LAB"):
            im = im.convert(mode)
        im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                      srgb, outputMode=mode)
        profile = srgb.tobytes()
    else:
        im = im.convert(mode)
    # Avoid accidentally carrying EXIF, thumbnails, or PNG text into each trial encode.
    im.info.clear()
    return im, profile


def encode_image(im: Image.Image, fmt: str, quality: int, profile: bytes | None) -> bytes:
    options = {"icc_profile": profile} if profile else {}
    if fmt == "JPEG":
        options.update(quality=quality, optimize=True, progressive=True, subsampling=2)
    elif fmt == "WEBP":
        options.update(quality=quality, method=4)
    else:
        options.update(optimize=True, compress_level=9)
    with io.BytesIO() as buffer:
        im.save(buffer, format=fmt, **options)
        return buffer.getvalue()


def fit_image(im: Image.Image, fmt: str, profile: bytes | None, target: int,
              cancel: threading.Event) -> tuple[bytes, tuple[int, int]]:
    """Search quality first, then resize from original pixels (no repeated JPEG loss)."""
    current = im
    try:
        for _ in range(35):
            check_cancel(cancel)
            high_data = encode_image(current, fmt, 95, profile)
            if len(high_data) <= target:
                return high_data, current.size
            if fmt in {"JPEG", "WEBP"}:
                check_cancel(cancel)
                low_data = encode_image(current, fmt, 60, profile)
                if len(low_data) <= target:
                    best = low_data
                    low, high = 61, 94
                    while low <= high:
                        check_cancel(cancel)
                        middle = (low + high) // 2
                        candidate = encode_image(current, fmt, middle, profile)
                        if len(candidate) <= target:
                            best, low = candidate, middle + 1
                        else:
                            high = middle - 1
                    return best, current.size
            else:
                low_data = high_data
            ratio = min(0.90, max(0.10, math.sqrt(target / len(low_data)) * 0.95))
            size = tuple(max(1, int(side * ratio)) for side in current.size)
            if size == current.size:
                break
            if current is not im:
                current.close()
            current = im.resize(size, Image.Resampling.LANCZOS)
        raise ValueError("无法在目标大小内生成可用图片，已保留原件")
    finally:
        if current is not im:
            current.close()


def process_file(source: Path, destination: Path, target: int, occupied: set[str],
                 cancel: threading.Event):
    before = source.stat().st_size
    ext = source.suffix.lower()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            opened_context = Image.open(source)
        except UnidentifiedImageError:
            if ext in IMAGE_EXTENSIONS:
                raise
            write_file(destination, cancel, source=source)
            status = "保留未压缩" if ext in UNSUPPORTED_IMAGES else "复制其他文件"
            note = "暂不支持此图片格式" if ext in UNSUPPORTED_IMAGES else "非图片，原样复制"
            return destination, status, note, before, before
        with opened_context as opened:
            original_format = opened.format or ""
            if original_format not in SUPPORTED_FORMATS:
                write_file(destination, cancel, source=source)
                return destination, "保留未压缩", f"暂不支持 {original_format or '此'} 图片格式", before, before
            frames = getattr(opened, "n_frames", 1)
            if frames > 1:
                write_file(destination, cancel, source=source)
                note = f"多帧/多页图片（{frames} 帧），保留全部内容"
                if before > target:
                    note += "；超过目标大小"
                return destination, "保留未压缩", note, before, before
            opened.load()
            if before <= target:
                if ext not in VALID_SUFFIXES[original_format]:
                    corrected = reserve_name(destination.stem + CANONICAL_SUFFIX[original_format], occupied)
                    destination = destination.with_name(corrected)
                write_file(destination, cancel, source=source)
                note = "小于或等于目标，原样复制"
                if ext not in VALID_SUFFIXES[original_format]:
                    note += f"；扩展名修正为 {CANONICAL_SUFFIX[original_format]}"
                return destination, "已达标", note, before, before
            check_cancel(cancel)
            im, profile = prepare_image(opened)
    try:
        if original_format == "PNG":
            fmt, suffix = "PNG", ".png"
        elif original_format == "WEBP":
            fmt, suffix = "WEBP", ".webp"
        elif im.mode == "RGBA":
            fmt, suffix = "PNG", ".png"
        else:
            fmt, suffix = "JPEG", ".jpg"
        original_size = im.size
        data, size = fit_image(im, fmt, profile, target, cancel)
        if len(data) > target:
            raise ValueError("编码结果超过目标大小")
        same_format = original_format == fmt and (
            (fmt == "JPEG" and ext in {".jpg", ".jpeg", ".jpe", ".jfif"}) or ext == suffix
        )
        if not same_format:
            name = reserve_name(destination.stem + suffix, occupied)
            destination = destination.with_name(name)
        write_file(destination, cancel, data=data, source=source)
        note = f"{original_size[0]}×{original_size[1]} → {size[0]}×{size[1]}"
        if not same_format:
            note += f"；转为 {fmt}"
        return destination, "已压缩", note, before, len(data)
    finally:
        im.close()


def csv_cell(value):
    text = str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def normalize_sources(source) -> tuple[Path, str, list[Path] | None]:
    if isinstance(source, (str, os.PathLike)):
        path = Path(source).expanduser().resolve()
        if path.is_symlink():
            raise ValueError("不能直接处理链接，请选择其实际文件或文件夹")
        if path.is_dir():
            return path, path.name, None
        if path.is_file():
            return path.parent, path.stem, [path]
        raise ValueError("请选择存在的图片或文件夹")
    try:
        paths = list(dict.fromkeys(Path(item).expanduser().resolve() for item in source))
    except (TypeError, ValueError):
        raise ValueError("请选择图片或文件夹") from None
    if not paths or any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValueError("一次可选择一个文件夹，或同一目录中的一张/多张图片")
    parents = {path.parent for path in paths}
    if len(parents) != 1:
        raise ValueError("多张图片需位于同一个文件夹；也可以选择它们的共同文件夹")
    return paths[0].parent, "所选图片", paths


def run_batch(source, target_bytes: int = 1_000_000,
              cancel: threading.Event | None = None,
              emit: Callable[[dict], None] | None = None) -> BatchResult:
    if not isinstance(target_bytes, int) or target_bytes < 10_000:
        raise ValueError("目标大小至少为 0.01 MB")
    root, source_name, selected = normalize_sources(source)
    if root.parent == root:
        raise ValueError("请选择磁盘内的文件夹，不能直接选择磁盘根目录")
    cancel = cancel if cancel is not None else threading.Event()
    emit = emit or (lambda event: None)
    if selected is None:
        folders, items, reserved = scan_folder(root, cancel, emit)
    else:
        folders = []
        items = [(path.relative_to(root), "file", "") for path in sorted(selected, key=lambda p: name_key(p.name))]
        reserved = {Path("."): {name_key(entry.name) for entry in root.iterdir()}}
    check_cancel(cancel)
    output = new_output(root if selected is not None else root.parent, source_name)
    report = output / reserve_name("_压缩报告.csv", reserved.setdefault(Path("."), set()))
    result = BatchResult(output=output, report=report, total=len(items))
    emit({"type": "start", "total": result.total, "output": str(output)})
    with report.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["原文件", "输出文件", "状态", "原大小(字节)", "新大小(字节)",
                         "目标大小(字节)", "说明"])
        try:
            for folder in folders:
                check_cancel(cancel)
                try:
                    (output / folder).mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    result.errors += 1
                    writer.writerow([csv_cell(folder), "", "异常", 0, 0, target_bytes, csv_cell(exc)])
            for relative, kind, detail in items:
                check_cancel(cancel)
                emit({"type": "current", "path": str(relative)})
                src, dst = root / relative, output / relative
                before = after = 0
                if kind != "file":
                    status = "跳过" if kind == "skip" else "异常"
                    note = detail
                    result.skipped += kind == "skip"
                    result.errors += kind == "error"
                    shown_dst = ""
                else:
                    try:
                        before = src.stat().st_size
                        dst, status, note, before, after = process_file(
                            src, dst, target_bytes, reserved.setdefault(relative.parent, set()), cancel)
                        shown_dst = str(dst.relative_to(output))
                        if status == "已压缩":
                            result.compressed += 1
                        elif status == "已达标":
                            result.unchanged += 1
                        elif status == "保留未压缩":
                            result.preserved += 1
                        else:
                            result.other += 1
                    except Cancelled:
                        raise
                    except Exception as exc:
                        result.errors += 1
                        status, shown_dst = "异常", ""
                        note = f"{type(exc).__name__}: {exc}"
                        try:
                            write_file(output / relative, cancel, source=src)
                            after = before
                            shown_dst = str(relative)
                            note += "；已复制原件（可能未达标）"
                        except Cancelled:
                            raise
                        except Exception as copy_exc:
                            note += f"；原件复制失败：{copy_exc}"
                            error_code = getattr(copy_exc, "errno", None) or getattr(exc, "errno", None)
                            if error_code in FATAL_IO:
                                result.fatal_error = f"写入失败，任务已停止：{copy_exc}"
                result.processed += 1
                result.input_bytes += before
                result.output_bytes += after
                if shown_dst:
                    result.saved_bytes += max(0, before - after)
                row = [relative, shown_dst, status, before, after, target_bytes, note]
                writer.writerow([csv_cell(value) for value in row])
                handle.flush()
                emit({"type": "file", "path": str(relative), "output": shown_dst, "status": status,
                      "before": before, "after": after, "note": note, "done": result.processed,
                      "total": result.total, "saved": result.saved_bytes})
                if result.fatal_error:
                    break
        except Cancelled:
            result.cancelled = True
        finally:
            summary = f"已处理 {result.processed}/{result.total}；压缩 {result.compressed}；已达标 {result.unchanged}；其他文件 {result.other}；保留未压缩 {result.preserved}；异常 {result.errors}；跳过 {result.skipped}"
            end_status = "处理失败，副本未完整" if result.fatal_error else "已取消，副本不完整" if result.cancelled else "处理结束"
            writer.writerow(["【任务汇总】", "", end_status,
                             result.input_bytes, result.output_bytes, target_bytes, summary])
    return result
