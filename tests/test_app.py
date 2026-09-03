import time
from types import SimpleNamespace

from PIL import Image
from app import App


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
        assert str(app.start_button.cget("state")) == "disabled"
        # Generate the same Tcl list shape as an Explorer folder-drop event.
        drop_data = app.tk.call("format", "%s", app.tk.call("list", str(source)))
        event = SimpleNamespace(data=drop_data, action="copy")
        assert app._drop(event) == "copy"
        assert app.path.get() == str(source)
        app.start_button.invoke()
        assert app.busy
        assert str(app.start_button.cget("state")) == "disabled"
        end = time.monotonic() + 15
        while app.busy and time.monotonic() < end:
            app.update()
            time.sleep(0.03)
        assert not app.busy
        assert app.result is not None
        assert app.result.errors == 0
        assert app.state_text.get() == "处理完成"
        assert str(app.open_button.cget("state")) == "normal"
        assert (app.result.output / "小图.jpg").exists()
    finally:
        app.destroy()


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
        app.destroy()


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
        end = time.monotonic() + 15
        while app.busy and time.monotonic() < end:
            app.update()
            time.sleep(0.03)
        assert app.result.errors == 0
        assert (app.result.output / source.name).exists()
    finally:
        app.destroy()
