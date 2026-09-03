import time
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from app import App


def test_destroyed_window_can_be_collected_by_next_worker():
    # Isolate this regression: the broken version aborts inside Tcl, bypassing pytest.
    code = '''
import gc, sys, threading
from app import App
errors = []
sys.unraisablehook = lambda event: errors.append(str(event.exc_value))
gc.disable()
window = App()
window.update()
window.destroy()
del window
worker = threading.Thread(target=gc.collect)
worker.start()
worker.join(timeout=20)
assert not worker.is_alive()
assert not errors, errors
'''
    result = subprocess.run([sys.executable, "-c", code],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def wait_until_finished(app, timeout=60):
    end = time.monotonic() + timeout
    while app.busy and time.monotonic() < end:
        app.update()
        time.sleep(0.03)
    assert not app.busy
    if app.worker:
        app.worker.join(timeout=2)
        assert not app.worker.is_alive()


def close_after_worker(app):
    if app.busy:
        app.cancel_event.set()
        end = time.monotonic() + 60
        while app.busy and time.monotonic() < end:
            app.update()
            time.sleep(0.03)
    if app.worker:
        app.worker.join(timeout=2)
        assert not app.worker.is_alive()
    app.destroy()


def test_gui_drop_process_and_result_folder_button(tmp_path):
    source = tmp_path / "拖入 空格 {花括号}"
    source.mkdir()
    Image.new("RGB", (120, 80), "red").save(source / "小图.jpg")
    app = App()
    try:
        app.update()
        for height in (620, 680, 720, 880):
            app.geometry(f"960x{height}")
            app.update()
            assert app.open_button.winfo_ismapped()
            assert app.open_button.winfo_rooty() + app.open_button.winfo_height() <= app.winfo_rooty() + app.winfo_height()
            assert app.table.winfo_height() >= 64
        assert str(app.start_button.cget("state")) == "disabled"
        # Generate the same Tcl list shape as an Explorer folder-drop event.
        drop_data = app.tk.call("format", "%s", app.tk.call("list", str(source)))
        event = SimpleNamespace(data=drop_data, action="copy")
        assert app._drop(event) == "copy"
        assert app.path.get() == str(source)
        app.start_button.invoke()
        assert app.busy
        assert str(app.start_button.cget("state")) == "disabled"
        wait_until_finished(app)
        assert app.result is not None
        assert app.result.errors == 0
        assert app.state_text.get() == "处理完成"
        assert str(app.open_button.cget("state")) == "normal"
        assert (app.result.output / "小图.jpg").exists()
    finally:
        close_after_worker(app)


def test_gui_rejects_files_from_different_folders(monkeypatch, tmp_path):
    first = tmp_path / "a" / "1.jpg"
    second = tmp_path / "b" / "2.jpg"
    for path in (first, second):
        path.parent.mkdir()
        Image.new("RGB", (10, 10)).save(path)
    messages = []
    monkeypatch.setattr("app.messagebox.showinfo", lambda *args, **kwargs: messages.append(args))
    app = App()
    try:
        event = SimpleNamespace(data=app.tk.call("list", str(first), str(second)), action="copy")
        assert app._drop(event) == "break"
        assert not app.sources
        assert messages
    finally:
        close_after_worker(app)


def test_gui_accepts_single_image_drop(tmp_path):
    source = tmp_path / "单张.jpg"
    Image.new("RGB", (100, 80), "blue").save(source)
    app = App()
    try:
        app.update()
        event = SimpleNamespace(data=app.tk.call("list", str(source)), action="copy")
        assert app._drop(event) == "copy"
        assert app.sources == [source]
        app.start_button.invoke()
        wait_until_finished(app)
        assert app.result.errors == 0
        assert (app.result.output / source.name).exists()
    finally:
        close_after_worker(app)
