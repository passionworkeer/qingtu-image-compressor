from pathlib import Path
import app as app_module
from app import App


def test_open_result_uses_macos_open(monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda args: opened.append(args))
    instance = App()
    try:
        instance.output_folder = tmp_path
        instance._open_output()
        assert opened == [["open", str(tmp_path)]]
    finally:
        instance.destroy()
