"""Double-click desktop app. All processing stays on this computer."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from tkinterdnd2 import DND_FILES, TkinterDnD
from compressor import BatchResult, Cancelled, run_batch

BLUE = "#4F46E5"
INK = "#1E1B4B"
MUTED = "#5B6172"
BG = "#F6F7FB"


def file_size(value):
    if value < 1_000:
        return f"{value} B"
    if value < 1_000_000:
        return f"{value / 1000:.1f} KB"
    if value < 1_000_000_000:
        return f"{value / 1_000_000:.2f} MB"
    return f"{value / 1_000_000_000:.2f} GB"


class App(TkinterDnD.Tk):
    def __init__(self, folder=""):
        super().__init__()
        self.title("轻图 · 批量图片压缩")
        self.configure(bg=BG)
        self.geometry(f"920x{min(820, self.winfo_screenheight() - 80)}")
        self.minsize(780, 620)
        icon = Path(__file__).with_name("app.ico")
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass
        png_icon = Path(__file__).with_name("app_icon.png")
        if png_icon.exists():
            try:
                self._icon_image = tk.PhotoImage(file=str(png_icon))
                self.iconphoto(True, self._icon_image)
            except tk.TclError:
                pass
        self.font_family = "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(name).configure(family=self.font_family, size=10)
        initial = Path(folder).expanduser() if folder else None
        self.sources = [initial] if initial and initial.exists() else []
        self.path = tk.StringVar(value=str(initial) if initial else "")
        self.target = tk.StringVar(value="1")
        self.state_text = tk.StringVar(value="准备就绪")
        self.detail_text = tk.StringVar(value="选择文件夹后，点击开始压缩。")
        self.output_text = tk.StringVar(value="文件夹生成同级副本；单图生成在图片所在目录。原件始终不改。")
        self.metrics = tk.StringVar(value="已处理 0 项    ·    节省 0 B")
        self.cancel_event = threading.Event()
        self.events = queue.Queue(maxsize=300)
        self.busy = False
        self.closing = False
        self.worker = None
        self.result = None
        self.output_folder = None
        self.started = 0.0
        self.last_scan = 0.0
        self._styles()
        self._layout()
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._drop)
        for widget in (self.drop_area, self.path_entry):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._drop)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._poll)
        self._path_changed()

    def _styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TButton", padding=(14, 10), font=(self.font_family, 10),
                    background="#FFFFFF", foreground=INK, bordercolor="#DCE2ED", relief="flat")
        s.map("TButton", background=[("active", "#EDF2FA"), ("disabled", "#F0F2F6")],
              foreground=[("disabled", "#9CA5B5")])
        s.configure("Primary.TButton", background=BLUE, foreground="white", borderwidth=0)
        s.map("Primary.TButton", background=[("disabled", "#A6BCED"), ("active", "#1D50C9")],
              foreground=[("disabled", "#FFFFFF")])
        s.configure("TEntry", padding=9, fieldbackground="white", bordercolor="#DCE2ED")
        s.configure("TSpinbox", padding=8, fieldbackground="white", bordercolor="#DCE2ED")
        s.configure("Horizontal.TProgressbar", background=BLUE, troughcolor="#E8EDF6",
                    borderwidth=0, lightcolor=BLUE, darkcolor=BLUE)
        s.configure("Treeview", background="white", fieldbackground="white", foreground=INK,
                    rowheight=32, borderwidth=0, font=(self.font_family, 9))
        s.configure("Treeview.Heading", background="#F1F4F9", foreground=MUTED,
                    font=(self.font_family, 9), relief="flat", padding=(8, 8))
        s.map("Treeview", background=[("selected", "#DDE8FF")],
              foreground=[("selected", INK)])

    def label(self, parent, text=None, **kwargs):
        options = dict(bg=parent.cget("bg"), fg=INK, anchor="w")
        options.update(kwargs)
        return tk.Label(parent, text=text, **options)

    def _layout(self):
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=30, pady=(16, 12))
        top = tk.Frame(container, bg=BG)
        top.pack(fill="x")
        self.label(top, "轻图", font=(self.font_family, 23, "bold")).pack(side="left")
        self.label(top, "图片压缩", font=(self.font_family, 12), fg=MUTED).pack(side="left", padx=12, pady=(9, 0))
        self.label(top, "100% 本地 · 原图保留", fg="#087A61", font=(self.font_family, 10)).pack(side="right", pady=(9, 0))
        self.label(container, "拖进来，压到 1 MB 左右。单图和整文件夹都可以。", fg=MUTED).pack(fill="x", pady=(3, 8))

        card = tk.Frame(container, bg="white", highlightbackground="#E1E6EF", highlightthickness=1)
        card.pack(fill="x")
        self.drop_area = tk.Canvas(card, height=88, bg="#F3F3FF", highlightthickness=0, cursor="hand2")
        self.drop_area.pack(fill="x", padx=16, pady=(10, 8))
        self.drop_area.bind("<Configure>", self._draw_drop)
        self.drop_area.bind("<Button-1>", lambda _: self._choose_folder())
        row = tk.Frame(card, bg="white")
        row.pack(fill="x", padx=18)
        self.path_entry = ttk.Entry(row, textvariable=self.path, state="readonly")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.choose_button = ttk.Button(row, text="选择文件夹", command=self._choose_folder)
        self.choose_button.pack(side="right")
        self.choose_images_button = ttk.Button(row, text="选择图片", command=self._choose_images)
        self.choose_images_button.pack(side="right", padx=(0, 8))
        self.label(card, "选文件夹会下钻全部子目录；单图和同一目录中的多图也可一次处理。", fg=MUTED,
                   font=(self.font_family, 9)).pack(fill="x", padx=18, pady=(6, 8))
        controls = tk.Frame(card, bg="white")
        controls.pack(fill="x", padx=18, pady=(0, 12))
        self.label(controls, "压到每张").pack(side="left", padx=(0, 9))
        self.target_input = ttk.Spinbox(controls, from_=0.1, to=20, increment=0.1,
                                        textvariable=self.target, width=5)
        self.target_input.pack(side="left")
        self.label(controls, "MB 以内", fg=MUTED).pack(side="left", padx=9)
        self.label(controls, "1 MB = 1,000,000 字节", fg=MUTED, font=(self.font_family, 9)).pack(side="left", padx=8)
        self.start_button = ttk.Button(controls, text="开始压缩", style="Primary.TButton", command=self._start)
        self.start_button.pack(side="right")
        self.cancel_button = ttk.Button(controls, text="取消", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="right", padx=(0, 9))

        status = tk.Frame(container, bg=BG)
        status.pack(fill="x", pady=(12, 6))
        self.status_label = self.label(status, textvariable=self.state_text, font=(self.font_family, 12, "bold"))
        self.status_label.pack(side="left")
        self.label(status, textvariable=self.metrics, fg=MUTED, font=(self.font_family, 9)).pack(side="right")
        self.progress = ttk.Progressbar(container, mode="determinate", maximum=100)
        self.progress.pack(fill="x", ipady=2)
        self.label(container, textvariable=self.detail_text, fg=MUTED, font=(self.font_family, 9)).pack(fill="x", pady=(6, 7))

        table_frame = tk.Frame(container, bg="white", highlightbackground="#E1E6EF", highlightthickness=1)
        table_frame.pack(fill="both", expand=True)
        columns = ("path", "before", "after", "status")
        self.table = ttk.Treeview(table_frame, columns=columns, show="headings", height=5)
        for key, name, width in zip(columns, ("文件 / 相对路径", "原大小", "处理后", "结果"), (450, 108, 108, 118)):
            self.table.heading(key, text=name, anchor="w")
            self.table.column(key, width=width, minwidth=75, stretch=key == "path", anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.table.tag_configure("good", foreground="#21816A")
        self.table.tag_configure("warning", foreground="#A96916")
        self.table.tag_configure("error", foreground="#BC4150")
        self.table.bind("<<TreeviewSelect>>", self._select_row)
        self.row_notes = {}
        footer = tk.Frame(container, bg=BG)
        footer.pack(side="bottom", before=table_frame, fill="x", pady=(8, 0))
        self.output_label = self.label(footer, textvariable=self.output_text, fg=MUTED,
                                       font=(self.font_family, 9), wraplength=550, justify="left")
        self.output_label.pack(side="left", fill="x", expand=True)
        self.open_button = ttk.Button(footer, text="打开结果文件夹", state="disabled", command=self._open_output)
        self.open_button.pack(side="right")
        self.label(container, "支持 JPG / PNG / WebP / HEIC / AVIF / BMP / TIFF / GIF。动图、多页图保留原件并提示。",
                   fg=MUTED, font=(self.font_family, 9)).pack(side="bottom", before=footer, fill="x", pady=(6, 0))

    def _draw_drop(self, event=None):
        c = self.drop_area
        w = c.winfo_width()
        c.delete("all")
        c.create_rectangle(1, 1, w - 2, 86, outline="#A9A7F3", dash=(7, 5))
        cx = w / 2
        c.create_rectangle(cx - 17, 8, cx + 17, 34, outline=BLUE, width=2)
        c.create_oval(cx + 5, 13, cx + 9, 17, fill=BLUE, outline=BLUE)
        c.create_line(cx - 13, 30, cx - 4, 21, cx + 2, 27, cx + 8, 23, cx + 13, 30, fill=BLUE, width=2)
        c.create_text(cx, 52, text="把图片或文件夹拖到这里", fill=INK, font=(self.font_family, 15, "bold"))
        c.create_text(cx, 74, text="文件夹会自动遍历所有子目录", fill=MUTED, font=(self.font_family, 9))

    def _set_sources(self, paths):
        self.sources = [Path(path).expanduser() for path in paths]
        if not self.sources:
            self.path.set("")
        elif len(self.sources) == 1:
            self.path.set(str(self.sources[0]))
        else:
            self.path.set(f"已选择 {len(self.sources)} 张图片 · {self.sources[0].parent}")
        self._path_changed()

    def _choose_folder(self):
        if self.busy:
            return
        chosen = filedialog.askdirectory(title="选择要压缩的图片文件夹", mustexist=True)
        if chosen:
            self._set_sources([chosen])

    def _choose_images(self):
        if self.busy:
            return
        chosen = filedialog.askopenfilenames(title="选择一张或多张图片",
            filetypes=[("常用图片", "*.jpg *.jpeg *.png *.webp *.heic *.heif *.avif *.bmp *.tif *.tiff *.gif"),
                       ("所有文件", "*.*")])
        if chosen:
            self._set_sources(chosen)

    def _drop(self, event):
        if self.busy:
            return "break"
        paths = self.tk.splitlist(event.data)
        candidates = [Path(path) for path in paths]
        valid = (len(candidates) == 1 and candidates[0].is_dir()) or (
            candidates and all(path.is_file() for path in candidates)
            and len({path.parent.resolve() for path in candidates}) == 1)
        if not valid:
            messagebox.showinfo("请选择图片或文件夹", "可拖入一个文件夹，或同一目录中的一张/多张图片。", parent=self)
            return "break"
        self._set_sources(candidates)
        return event.action

    def _path_changed(self):
        if not self.busy:
            self.start_button.configure(state="normal" if self.sources else "disabled")

    def _start(self):
        if self.busy:
            return
        if not self.sources or any(not path.exists() for path in self.sources):
            messagebox.showerror("文件不存在", "所选图片或文件夹已移动，请重新选择。", parent=self)
            return
        selection = self.sources[0] if len(self.sources) == 1 else list(self.sources)
        try:
            mb = Decimal(self.target.get())
            if not mb.is_finite() or not Decimal("0.1") <= mb <= 20:
                raise ValueError()
            target = int(mb * 1_000_000)
        except (ValueError, InvalidOperation):
            messagebox.showerror("目标大小无效", "请输入 0.1 到 20 之间的数字，例如 1。", parent=self)
            return
        self.busy = True
        self.result = None
        self.output_folder = None
        self.cancel_event.clear()
        self.started = time.monotonic()
        self.last_scan = 0.0
        self.table.delete(*self.table.get_children())
        self.row_notes.clear()
        for widget in (self.path_entry, self.choose_button, self.choose_images_button, self.target_input, self.start_button, self.open_button):
            widget.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.state_text.set("正在扫描文件夹…")
        self.detail_text.set("正在查找图片和子文件夹，请稍候。")
        self.metrics.set("已处理 0 项    ·    节省 0 B")
        self.output_text.set("正在准备副本文件夹…")
        self.status_label.configure(fg=INK)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.worker = threading.Thread(target=self._worker, args=(selection, target), name="image-compressor")
        self.worker.start()

    def _emit(self, event):
        if event["type"] == "scan":
            now = time.monotonic()
            if now - self.last_scan < 0.15:
                return
            self.last_scan = now
        self.events.put(event)

    def _worker(self, selection, target):
        try:
            result = run_batch(selection, target, self.cancel_event, self._emit)
            self.events.put({"type": "done", "result": result})
        except Cancelled:
            self.events.put({"type": "cancelled"})
        except Exception as exc:
            self.events.put({"type": "error", "message": str(exc)})

    def _poll(self):
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            kind = event["type"]
            if kind == "scan":
                self.detail_text.set(f"已发现 {event['found']} 项，继续扫描子文件夹…")
            elif kind == "start":
                self.output_folder = Path(event["output"])
                self.output_text.set("结果位置：" + str(self.output_folder))
                self.progress.stop()
                self.progress.configure(mode="determinate", maximum=max(event["total"], 1), value=0)
                self.state_text.set("正在处理…")
            elif kind == "current":
                self.detail_text.set("正在处理：" + event["path"][-105:])
            elif kind == "file":
                status = event["status"]
                tag = "good" if status in ("已压缩", "已达标") else "warning" if status in ("保留未压缩", "跳过") else "error" if status == "异常" else ""
                item = self.table.insert("", "end", values=(event["path"], file_size(event["before"]),
                                                          file_size(event["after"]), status), tags=(tag,))
                self.row_notes[item] = event["path"] + "：" + event["note"]
                # Keep large batches responsive. The CSV always contains every result.
                rows = self.table.get_children()
                if len(rows) > 500:
                    self.row_notes.pop(rows[0], None)
                    self.table.delete(rows[0])
                self.table.see(item)
                self.progress.configure(value=event["done"])
                elapsed = int(time.monotonic() - self.started)
                self.metrics.set(f"{event['done']} / {event['total']} 项    ·    节省 {file_size(max(0, event['saved']))}    ·    {elapsed} 秒")
            elif kind in ("done", "error", "cancelled"):
                self._finished(event)
        if self.closing and not self.busy:
            self.destroy()
            return
        self.after(80, self._poll)

    def _finished(self, event):
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.path_entry.configure(state="readonly")
        for widget in (self.choose_button, self.choose_images_button, self.target_input):
            widget.configure(state="normal")
        self._path_changed()
        self.cancel_button.configure(state="disabled", text="取消")
        if self.output_folder:
            self.open_button.configure(state="normal")
        if event["type"] == "error":
            self.state_text.set("处理未完成")
            self.status_label.configure(fg="#BC4150")
            self.detail_text.set(event["message"])
            if not self.closing:
                messagebox.showerror("处理未完成", event["message"] + "\n原文件未修改；已生成的文件可在结果目录查看。", parent=self)
        elif event["type"] == "cancelled":
            self.state_text.set("已取消扫描")
            self.detail_text.set("尚未创建副本文件夹，原文件未修改。")
            self.output_text.set("可重新选择文件夹并开始。")
        else:
            r: BatchResult = event["result"]
            self.result = r
            caution = r.preserved + r.errors + r.skipped
            if r.fatal_error:
                self.state_text.set("处理失败 · 副本未完整")
            elif r.cancelled:
                self.state_text.set("已取消 · 副本尚未完整")
            elif caution:
                self.state_text.set(f"处理结束 · {caution} 项需查看")
            elif r.total == 0:
                self.state_text.set("处理结束 · 文件夹中没有文件")
            else:
                self.state_text.set("处理完成")
            self.status_label.configure(fg="#B42318" if r.fatal_error else "#B45309" if caution or r.cancelled else "#087A61")
            self.detail_text.set(r.fatal_error or f"压缩 {r.compressed} · 已达标 {r.unchanged} · 其他文件 {r.other} · 保留未压缩 {r.preserved} · 异常 {r.errors} · 跳过 {r.skipped}。完整明细见 CSV 报告。")
            self.output_text.set("结果位置：" + str(r.output))
            if not r.cancelled and not r.fatal_error:
                self.progress.configure(value=max(r.total, 1))

    def _select_row(self, _):
        selected = self.table.selection()
        if selected and not self.busy:
            note = self.row_notes.get(selected[0], "")
            self.detail_text.set(note[:115])

    def _cancel(self):
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled", text="取消中…")
        self.state_text.set("正在取消，等待当前图片处理结束…")

    def _open_output(self):
        if self.output_folder:
            try:
                if sys.platform == "win32":
                    os.startfile(self.output_folder)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(self.output_folder)])
                else:
                    subprocess.Popen(["xdg-open", str(self.output_folder)])
            except OSError as exc:
                messagebox.showerror("无法打开文件夹", str(exc), parent=self)

    def _close(self):
        if self.busy:
            self.closing = True
            self._cancel()
        else:
            self.destroy()


def main():
    parser = argparse.ArgumentParser(description="轻图批量图片压缩")
    parser.add_argument("folder", nargs="?", default="")
    parser.add_argument("--batch", help="命令行批处理一个文件夹")
    parser.add_argument("--target-mb", type=Decimal, default=Decimal("1"))
    parser.add_argument("--result-json", type=Path)
    args = parser.parse_args()
    if args.batch:
        try:
            result = run_batch(args.batch, int(args.target_mb * 1_000_000))
            data = asdict(result)
            data["output"] = str(result.output)
            data["report"] = str(result.report)
            code = 2 if result.errors or result.skipped or result.preserved or result.fatal_error else 0
        except Exception as exc:
            data, code = {"error": str(exc)}, 1
        if args.result_json:
            args.result_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if sys.stdout:
            print(json.dumps(data, ensure_ascii=False))
        return code
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    App(args.folder).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
