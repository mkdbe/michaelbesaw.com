#!/usr/bin/env python3
"""
photo-uploader.py — michaelbesaw.com Photo Management Tool
------------------------------------------------------------
Drag & drop photos to process and rsync to server.
Delete photos from server by filename.

Web version:    max 2560px, 750KB–2MB, EXIF preserved → /photos/
Mobile version: max 1080px, ~150–280KB, EXIF preserved → /photos-mobile/

Requirements:
    pip install Pillow piexif tkinterdnd2

Usage:
    python3 photo-uploader.py
"""

import os
import sys
import threading
import subprocess
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image
    import piexif
except ImportError:
    print("Run: pip install Pillow piexif")
    sys.exit(1)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    print("Run: pip install tkinterdnd2")
    sys.exit(1)

# ── Server Config ─────────────────────────────────────────────────────────────
RSYNC_USER_HOST  = "mdbe@linode"
REMOTE_WEB_DIR   = "/var/www/michaelbesaw.com/photos/"
REMOTE_MOBILE_DIR= "/var/www/michaelbesaw.com/photos-mobile/"
RSYNC_CMD        = "rsync"
RSYNC_FLAGS      = ["-avhi", "--perms"]
SSH_CMD          = "ssh"

# ── Processing Config ─────────────────────────────────────────────────────────
WEB_MAX_DIM      = 2560
WEB_MIN_KB       = 750
WEB_MAX_KB       = 2000
WEB_QUALITY      = 88

MOBILE_MAX_DIM   = 1080
MOBILE_MAX_KB    = 280
MOBILE_QUALITY   = 82

SUPPORTED_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".bmp"}

# ── Colors (HMS Inventory design system) ──────────────────────────────────────
BG       = "#0a0a0a"       # near-black
BG2      = "#0e0e0e"       # header
SURF     = "#141414"       # surfaces
SURF2    = "#1a1a1a"       # buttons
SURF3    = "#222222"       # hover
BORDER   = "#2a2a2a"       # borders
RED      = "#c0392b"       # delete actions
RED2     = "#e04030"       # delete hover
WHITE    = "#ffffff"
OFF      = "#e0e0e0"       # primary text
MUTED    = "#999999"       # secondary text
MUTED2   = "#666666"       # tertiary text
GOOD     = "#3aaa74"       # upload ready
WARN     = "#d4922a"
# ─────────────────────────────────────────────────────────────────────────────

FONT     = "Helvetica Neue"
FONT_M   = "Menlo"


class AutoScrollbar(tk.Scrollbar):
    """Scrollbar that hides itself when not needed."""
    def set(self, lo, hi):
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.pack_forget()
        else:
            if not self.winfo_ismapped():
                self.pack(side="right", fill="y", pady=6, padx=(0, 2))
        tk.Scrollbar.set(self, lo, hi)


def get_exif(img):
    try:
        return img.info.get("exif")
    except Exception:
        return None


def resize_image(img, max_dim):
    w, h = img.size
    if w <= max_dim and h <= max_dim:
        return img
    if w >= h:
        return img.resize((max_dim, int(h * max_dim / w)), Image.LANCZOS)
    else:
        return img.resize((int(w * max_dim / h), max_dim), Image.LANCZOS)


def to_rgb(img):
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (0, 0, 0))
        if img.mode == "P":
            img = img.convert("RGBA")
        mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
        bg.paste(img, mask=mask)
        return bg
    elif img.mode != "RGB":
        return img.convert("RGB")
    return img


def save_jpeg(img, path, exif_bytes, quality, min_kb=None, max_kb=None):
    q = quality
    while q >= 55:
        kwargs = {"format": "JPEG", "quality": q, "optimize": True, "progressive": True}
        if exif_bytes:
            kwargs["exif"] = exif_bytes
        img.save(path, **kwargs)
        size_kb = os.path.getsize(path) / 1024
        if max_kb and size_kb > max_kb:
            q -= 5
            continue
        if min_kb and size_kb < min_kb and q < quality:
            q = min(quality, q + 5)
            kwargs["quality"] = q
            if exif_bytes:
                kwargs["exif"] = exif_bytes
            img.save(path, **kwargs)
        break
    return os.path.getsize(path)


def process_photo(src_path, web_dir, mobile_dir):
    """Process one photo into web and mobile versions."""
    src = Path(src_path)
    out_name = src.stem + ".jpg"
    web_out = web_dir / out_name
    mobile_out = mobile_dir / out_name

    with Image.open(src) as img:
        img = to_rgb(img)
        exif_bytes = get_exif(img)
        web_img = resize_image(img, WEB_MAX_DIM)
        web_size = save_jpeg(web_img, web_out, exif_bytes, WEB_QUALITY, WEB_MIN_KB, WEB_MAX_KB)
        mob_img = resize_image(img, MOBILE_MAX_DIM)
        mob_size = save_jpeg(mob_img, mobile_out, exif_bytes, MOBILE_QUALITY, max_kb=MOBILE_MAX_KB)

    return web_out, mobile_out, {
        "original_kb": os.path.getsize(src) / 1024,
        "web_kb": web_size / 1024,
        "mobile_kb": mob_size / 1024,
        "web_dim": web_img.size,
        "mobile_dim": mob_img.size,
    }


class PhotoUploaderApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("michaelbesaw — photo manager")
        self.configure(bg=BG)
        self.geometry("700x620")
        self.resizable(True, True)
        self.minsize(600, 500)

        self.queued_files = []
        self.delete_files = []
        self.processing = False
        self.current_page = "upload"

        self._build_ui()

    def _make_btn(self, parent, text, command, side="left"):
        """HMS-style button: dark surface, 1px border, hover brightens."""
        f = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        lbl = tk.Label(f, text=text, font=(FONT, 10, "bold"),
                       bg=SURF2, fg=MUTED, padx=16, pady=8, cursor="hand2")
        lbl.pack()
        f.pack(side=side, padx=(0, 8) if side == "left" else (8, 0))

        def on_enter(e):
            lbl.config(bg=SURF3, fg=OFF)
        def on_leave(e):
            # Respect override border if set
            lbl.config(bg=SURF2, fg=MUTED)
        def on_press(e):
            if lbl.cget("state") != "disabled":
                command()

        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        lbl.bind("<Button-1>", on_press)
        lbl._frame = f
        return lbl

    def _make_red_btn(self, parent, text, command, side="left"):
        """HMS-style red accent button (like Add to Inventory / primary actions)."""
        f = tk.Frame(parent, bg=RED, padx=1, pady=1)
        lbl = tk.Label(f, text=text, font=(FONT, 11, "bold"),
                       bg=RED, fg=WHITE, padx=20, pady=10, cursor="hand2")
        lbl.pack()
        f.pack(side=side, padx=(0, 8) if side == "left" else (8, 0))

        def on_enter(e): lbl.config(bg=RED2)
        def on_leave(e): lbl.config(bg=RED)
        def on_press(e):
            if lbl.cget("state") != "disabled":
                command()

        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        lbl.bind("<Button-1>", on_press)
        lbl._frame = f
        return lbl

    def _build_ui(self):
        main_wrap = tk.Frame(self, bg=BG)
        main_wrap.pack(side="left", fill="both", expand=True)

        # ── Header ──
        hdr = tk.Frame(main_wrap, bg=BG2, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        hdr_inner = tk.Frame(hdr, bg=BG2)
        hdr_inner.pack(fill="both", expand=True, padx=20)

        tk.Label(hdr_inner, text="michaelbesaw", font=(FONT, 11, "bold"),
                 bg=BG2, fg=MUTED, anchor="w").pack(side="left")

        sep_v = tk.Frame(hdr_inner, bg=BORDER, width=1, height=14)
        sep_v.pack(side="left", padx=14)

        self.page_title_label = tk.Label(hdr_inner, text="UPLOAD PHOTOS",
                                          font=(FONT, 9, "bold"), bg=BG2, fg=MUTED2)
        self.page_title_label.pack(side="left")

        # Toggle button in header
        self.toggle_btn = self._make_btn(hdr_inner, "DELETE FROM SERVER",
                                          self._toggle_page, side="right")

        sep_h = tk.Frame(main_wrap, bg=BORDER, height=1)
        sep_h.pack(fill="x")

        # ── Content ──
        self.content = tk.Frame(main_wrap, bg=BG)
        self.content.pack(fill="both", expand=True)

        self._build_upload_page()
        self._build_delete_page()

        # ── Shared log ──
        log_header = tk.Frame(main_wrap, bg=BG)
        log_header.pack(fill="x", padx=20, pady=(8, 3))
        tk.Label(log_header, text="LOG", font=(FONT, 8, "bold"),
                 bg=BG, fg=MUTED2).pack(side="left")

        log_frame = tk.Frame(main_wrap, bg=SURF, highlightthickness=1,
                             highlightbackground=BORDER)
        log_frame.pack(fill="x", padx=20, pady=(0, 16))

        self.log_text = tk.Text(
            log_frame, height=6, bg=SURF, fg=MUTED,
            insertbackground=SURF, font=(FONT_M, 10),
            borderwidth=0, highlightthickness=0,
            state="disabled", wrap="word",
        )
        log_scroll = AutoScrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self.log_text.bind("<MouseWheel>",
            lambda e: self.log_text.yview_scroll(-1*(e.delta//120), "units"))

        self._show_page("upload")

    def _build_upload_page(self):
        self.upload_page = tk.Frame(self.content, bg=BG)

        # Use grid so drop zone and file list get equal height
        panels = tk.Frame(self.upload_page, bg=BG)
        panels.pack(fill="both", expand=True, padx=20, pady=(14, 0))
        panels.grid_columnconfigure(0, weight=1)
        panels.grid_rowconfigure(0, weight=1, uniform="half")
        panels.grid_rowconfigure(1, weight=0)  # header row
        panels.grid_rowconfigure(2, weight=1, uniform="half")

        # ── Drop zone ──
        drop_frame = tk.Frame(panels, bg=SURF, bd=0, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=BORDER)
        drop_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        self.drop_label = tk.Label(
            drop_frame,
            text="drag photos here  ·  click to browse",
            font=(FONT, 11), bg=SURF, fg=MUTED2,
            padx=20, justify="center", cursor="hand2"
        )
        self.drop_label.pack(fill="both", expand=True)

        def drop_enter(e): self.drop_label.config(fg=MUTED)
        def drop_leave(e): self.drop_label.config(fg=MUTED2)

        drop_frame.drop_target_register(DND_FILES)
        drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_label.bind("<Enter>", drop_enter)
        self.drop_label.bind("<Leave>", drop_leave)
        drop_frame.bind("<Button-1>", self._browse_files)
        self.drop_label.bind("<Button-1>", self._browse_files)

        # ── List header ──
        list_header = tk.Frame(panels, bg=BG)
        list_header.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        tk.Label(list_header, text="QUEUED", font=(FONT, 8, "bold"),
                 bg=BG, fg=MUTED2).pack(side="left")
        self.count_label = tk.Label(list_header, text="0 files",
                                    font=(FONT, 8, "bold"), bg=BG, fg=MUTED2)
        self.count_label.pack(side="right")

        # ── File list ──
        lb_frame = tk.Frame(panels, bg=SURF, highlightthickness=1,
                            highlightbackground=BORDER)
        lb_frame.grid(row=2, column=0, sticky="nsew")

        self.file_listbox = tk.Listbox(
            lb_frame, bg=SURF, fg=OFF,
            selectbackground=SURF3, selectforeground=WHITE,
            font=(FONT_M, 11), borderwidth=0, highlightthickness=0,
            activestyle="none",
        )
        lb_scroll = AutoScrollbar(lb_frame, orient="vertical", command=self.file_listbox.yview)
        self.file_listbox.config(yscrollcommand=lb_scroll.set)
        self.file_listbox.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self.file_listbox.bind("<MouseWheel>",
            lambda e: self.file_listbox.yview_scroll(-1*(e.delta//120), "units"))
        self.file_listbox.bind("<Button-2>", self._remove_selected)
        self.file_listbox.bind("<Delete>", self._remove_selected)

        # ── Buttons ──
        btn_frame = tk.Frame(self.upload_page, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=(10, 0))

        self.clear_btn = self._make_btn(btn_frame, "CLEAR", self._clear_queue, side="left")

        # Upload button — border frame changes to green when files are queued
        self.upload_btn_frame = tk.Frame(btn_frame, bg=BORDER, padx=1, pady=1)
        self.upload_btn_label = tk.Label(
            self.upload_btn_frame, text="PROCESS + UPLOAD",
            font=(FONT, 11, "bold"), bg=SURF2, fg=MUTED,
            padx=20, pady=10, cursor="hand2"
        )
        self.upload_btn_label.pack()
        self.upload_btn_frame.pack(side="right", padx=(8, 0))

        def ul_enter(e):
            if self.queued_files:
                self.upload_btn_label.config(bg="#1a2e1a", fg=GOOD)
            else:
                self.upload_btn_label.config(bg=SURF3, fg=OFF)
        def ul_leave(e):
            if self.queued_files:
                self.upload_btn_label.config(bg=SURF2, fg=WHITE)
            else:
                self.upload_btn_label.config(bg=SURF2, fg=MUTED)
        def ul_press(e):
            self._start_upload()

        self.upload_btn_label.bind("<Enter>", ul_enter)
        self.upload_btn_label.bind("<Leave>", ul_leave)
        self.upload_btn_label.bind("<Button-1>", ul_press)

        self.progress_canvas = tk.Canvas(btn_frame, height=2, bg=BG,
                                         highlightthickness=0, bd=0)
        self._progress_active = False
        self._progress_pos = 0

    def _update_upload_btn_state(self):
        """Toggle green border on upload button based on queue state."""
        if self.queued_files:
            self.upload_btn_frame.config(bg=GOOD)
            self.upload_btn_label.config(fg=WHITE)
        else:
            self.upload_btn_frame.config(bg=BORDER)
            self.upload_btn_label.config(fg=MUTED)

    def _build_delete_page(self):
        self.delete_page = tk.Frame(self.content, bg=BG)

        # ── Filename entry ──
        entry_outer = tk.Frame(self.delete_page, bg=BG)
        entry_outer.pack(fill="x", padx=20, pady=(14, 8))

        tk.Label(entry_outer, text="enter filename to remove from server",
                 font=(FONT, 11), bg=BG, fg=MUTED2).pack(anchor="w", pady=(0, 8))

        entry_frame = tk.Frame(entry_outer, bg=BG)
        entry_frame.pack(fill="x")

        self.del_entry = tk.Entry(
            entry_frame, bg=SURF3, fg=OFF, insertbackground=OFF,
            font=(FONT_M, 12), borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor="#3a2020",
        )
        self.del_entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        self._del_placeholder = True
        self._set_del_placeholder()
        self.del_entry.bind("<FocusIn>", self._del_focus_in)
        self.del_entry.bind("<FocusOut>", self._del_focus_out)
        self.del_entry.bind("<Return>", self._add_delete_file)

        self.del_add_btn = self._make_btn(entry_frame, "ADD", self._add_delete_file, side="right")

        # ── Delete file list ──
        del_list_frame = tk.Frame(self.delete_page, bg=BG)
        del_list_frame.pack(fill="both", expand=True, padx=20)

        del_list_header = tk.Frame(del_list_frame, bg=BG)
        del_list_header.pack(fill="x", pady=(0, 4))
        tk.Label(del_list_header, text="QUEUED FOR DELETION", font=(FONT, 8, "bold"),
                 bg=BG, fg=MUTED2).pack(side="left")
        self.del_count_label = tk.Label(del_list_header, text="0 files",
                                         font=(FONT, 8, "bold"), bg=BG, fg=MUTED2)
        self.del_count_label.pack(side="right")

        del_lb_frame = tk.Frame(del_list_frame, bg=SURF, highlightthickness=1,
                                 highlightbackground=BORDER)
        del_lb_frame.pack(fill="both", expand=True)

        self.del_listbox = tk.Listbox(
            del_lb_frame, bg=SURF, fg=OFF,
            selectbackground=SURF3, selectforeground=WHITE,
            font=(FONT_M, 11), borderwidth=0, highlightthickness=0,
            activestyle="none",
        )
        self.del_listbox.pack(fill="both", expand=True, padx=8, pady=6)
        self.del_listbox.bind("<MouseWheel>",
            lambda e: self.del_listbox.yview_scroll(-1*(e.delta//120), "units"))
        self.del_listbox.bind("<Button-2>", self._remove_delete_selected)
        self.del_listbox.bind("<Delete>", self._remove_delete_selected)

        # ── Delete buttons ──
        del_btn_frame = tk.Frame(self.delete_page, bg=BG)
        del_btn_frame.pack(fill="x", padx=20, pady=(10, 0))

        self.del_clear_btn = self._make_btn(del_btn_frame, "CLEAR",
                                             self._clear_delete_queue, side="left")
        self.del_exec_btn = self._make_red_btn(del_btn_frame, "DELETE FROM SERVER",
                                                self._start_delete, side="right")

    # ── Page switching ──

    def _show_page(self, page):
        if page == "upload":
            self.delete_page.pack_forget()
            self.upload_page.pack(in_=self.content, fill="both", expand=True)
            self.current_page = "upload"
            self.page_title_label.config(text="UPLOAD PHOTOS")
            self.toggle_btn.config(text="DELETE FROM SERVER")
        else:
            self.upload_page.pack_forget()
            self.delete_page.pack(in_=self.content, fill="both", expand=True)
            self.current_page = "delete"
            self.page_title_label.config(text="DELETE FROM SERVER")
            self.toggle_btn.config(text="UPLOAD PHOTOS")

    def _toggle_page(self):
        if self.processing:
            return
        self._show_page("delete" if self.current_page == "upload" else "upload")

    # ── Shared ──

    def _log(self, msg, color=None):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── Upload page methods ──

    def _on_drop(self, event):
        files = self.tk.splitlist(event.data)
        self._add_files(files)

    def _browse_files(self, event=None):
        files = filedialog.askopenfilenames(
            title="Select Photos",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp *.tiff *.bmp"),
                       ("All files", "*.*")]
        )
        if files:
            self._add_files(files)

    def _add_files(self, files):
        added = 0
        for f in files:
            p = Path(f)
            if p.suffix.lower() in SUPPORTED_EXTS and p not in self.queued_files:
                self.queued_files.append(p)
                self.file_listbox.insert("end", p.name)
                added += 1
        if added:
            self._log(f"Added {added} file(s)")
        self.count_label.config(text=f"{len(self.queued_files)} file(s)")
        self._update_upload_btn_state()

    def _remove_selected(self, event=None):
        for i in reversed(self.file_listbox.curselection()):
            self.file_listbox.delete(i)
            del self.queued_files[i]
        self.count_label.config(text=f"{len(self.queued_files)} file(s)")
        self._update_upload_btn_state()

    def _clear_queue(self):
        self.queued_files.clear()
        self.file_listbox.delete(0, "end")
        self.count_label.config(text="0 files")
        self._update_upload_btn_state()
        self._log("Queue cleared")

    def _start_upload(self):
        if not self.queued_files:
            messagebox.showwarning("No files", "Add photos to the queue first.")
            return
        if self.processing:
            return
        self.processing = True
        self.upload_btn_label.config(text="PROCESSING…", fg=MUTED2, cursor="arrow")
        self.upload_btn_frame.config(bg=BORDER)
        self.progress_canvas.pack(side="right", fill="x", expand=True, padx=(12, 0))
        self._progress_active = True
        self._animate_progress()
        threading.Thread(target=self._process_and_upload, daemon=True).start()

    def _animate_progress(self):
        if not self._progress_active:
            return
        w = self.progress_canvas.winfo_width() or 200
        self.progress_canvas.delete("all")
        bar_w = 60
        x = self._progress_pos % (w + bar_w) - bar_w
        self.progress_canvas.create_rectangle(x, 0, x + bar_w, 2, fill=RED, outline="")
        self._progress_pos += 4
        self.after(30, self._animate_progress)

    def _fetch_server_filenames(self):
        """Return set of filenames already in /photos/ on the server."""
        result = subprocess.run(
            [SSH_CMD, RSYNC_USER_HOST, f"ls '{REMOTE_WEB_DIR}'"],
            capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Could not list server photos: {result.stderr.strip()}")
        return {name.strip() for name in result.stdout.splitlines() if name.strip()}

    def _process_and_upload(self):
        tmp = Path(tempfile.mkdtemp())
        web_dir = tmp / "photos"
        mobile_dir = tmp / "photos-mobile"
        web_dir.mkdir()
        mobile_dir.mkdir()

        try:
            self._log("\nChecking for duplicates on server…")
            existing = self._fetch_server_filenames()

            to_upload = []
            for src in self.queued_files:
                out_name = src.stem + ".jpg"
                if out_name in existing:
                    self._log(f"  ✗ skipping {src.name} — already on server")
                else:
                    to_upload.append(src)

            if not to_upload:
                self._log("\n✗ All queued photos already exist on server — nothing uploaded.")
                self.after(0, self._upload_complete)
                return

            if len(to_upload) < len(self.queued_files):
                skipped = len(self.queued_files) - len(to_upload)
                self._log(f"  {skipped} duplicate(s) skipped, {len(to_upload)} new photo(s) to upload\n")

            self._log(f"Processing {len(to_upload)} photo(s)…")
            for i, src in enumerate(to_upload):
                self._log(f"  [{i+1}/{len(to_upload)}] {src.name}")
                try:
                    _, _, info = process_photo(src, web_dir, mobile_dir)
                    self._log(f"    web:    {info['web_dim'][0]}×{info['web_dim'][1]}  {info['web_kb']:.0f}KB")
                    self._log(f"    mobile: {info['mobile_dim'][0]}×{info['mobile_dim'][1]}  {info['mobile_kb']:.0f}KB")
                except Exception as e:
                    self._log(f"    ERROR: {e}")

            self._log("\nUploading web photos…")
            self._rsync(str(web_dir) + "/", f"{RSYNC_USER_HOST}:{REMOTE_WEB_DIR}")
            self._log("Uploading mobile photos…")
            self._rsync(str(mobile_dir) + "/", f"{RSYNC_USER_HOST}:{REMOTE_MOBILE_DIR}")
            self._log(f"\n✓ Done — {len(to_upload)} photo(s) uploaded")
            self.after(0, self._upload_complete)
        except Exception as e:
            self._log(f"\n✗ Upload failed: {e}")
            self.after(0, self._upload_failed)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _rsync(self, src, dest):
        cmd = [RSYNC_CMD] + RSYNC_FLAGS + [src, dest]
        self._log(f"  rsync → {dest}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(result.stderr.strip())
        for line in result.stdout.strip().splitlines():
            if line and not line.startswith("sending") and not line.startswith("sent"):
                self._log(f"    {line}")

    def _upload_complete(self):
        self.processing = False
        self._progress_active = False
        self.progress_canvas.pack_forget()
        self.upload_btn_label.config(text="PROCESS + UPLOAD", cursor="hand2")
        self._clear_queue()
        self._log("✓ All photos processed and uploaded.")

    def _upload_failed(self):
        self.processing = False
        self._progress_active = False
        self.progress_canvas.pack_forget()
        self.upload_btn_label.config(text="PROCESS + UPLOAD", fg=MUTED, cursor="hand2")
        self.upload_btn_frame.config(bg=BORDER)
        self._log("✗ Upload failed. Check log above.")

    # ── Delete page methods ──

    def _set_del_placeholder(self):
        self.del_entry.delete(0, "end")
        self.del_entry.insert(0, "filename.jpg")
        self.del_entry.config(fg=MUTED2)
        self._del_placeholder = True

    def _del_focus_in(self, event=None):
        if self._del_placeholder:
            self.del_entry.delete(0, "end")
            self.del_entry.config(fg=OFF)
            self._del_placeholder = False

    def _del_focus_out(self, event=None):
        if not self.del_entry.get().strip():
            self._set_del_placeholder()

    def _add_delete_file(self, event=None):
        name = self.del_entry.get().strip()
        if not name or name == "filename.jpg":
            return
        if not name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            name += ".jpg"
        if name not in self.delete_files:
            self.delete_files.append(name)
            self.del_listbox.insert("end", name)
        self.del_entry.delete(0, "end")
        self.del_count_label.config(text=f"{len(self.delete_files)} file(s)")

    def _remove_delete_selected(self, event=None):
        for i in reversed(self.del_listbox.curselection()):
            self.del_listbox.delete(i)
            del self.delete_files[i]
        self.del_count_label.config(text=f"{len(self.delete_files)} file(s)")

    def _clear_delete_queue(self):
        self.delete_files.clear()
        self.del_listbox.delete(0, "end")
        self.del_count_label.config(text="0 files")
        self._log("Delete queue cleared")

    def _start_delete(self):
        if not self.delete_files:
            messagebox.showwarning("No files", "Add filenames to the delete queue first.")
            return
        if self.processing:
            return

        names = "\n".join(self.delete_files)
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete {len(self.delete_files)} photo(s) from server?\n\n{names}\n\n"
            "This removes from both /photos/ and /photos-mobile/."):
            return

        self.processing = True
        self.del_exec_btn.config(text="DELETING…", fg="#884444", cursor="arrow")
        threading.Thread(target=self._execute_delete, daemon=True).start()

    def _execute_delete(self):
        try:
            self._log(f"\nDeleting {len(self.delete_files)} photo(s) from server…")
            deleted = 0
            for name in self.delete_files:
                web_path = REMOTE_WEB_DIR + name
                mobile_path = REMOTE_MOBILE_DIR + name
                # Check existence and delete each path separately so we get honest feedback
                rm_cmd = (
                    f"([ -f '{web_path}' ] && rm '{web_path}' && echo 'deleted:web' || echo 'missing:web'); "
                    f"([ -f '{mobile_path}' ] && rm '{mobile_path}' && echo 'deleted:mobile' || echo 'missing:mobile')"
                )
                self._log(f"  rm {name}")
                result = subprocess.run(
                    [SSH_CMD, RSYNC_USER_HOST, rm_cmd],
                    capture_output=True, text=True)
                if result.returncode != 0:
                    self._log(f"    ERROR: {result.stderr.strip()}")
                else:
                    found = False
                    for line in result.stdout.strip().splitlines():
                        if line.startswith("deleted:"):
                            self._log(f"    ✓ removed from {line.split(':')[1]}")
                            found = True
                        elif line.startswith("missing:"):
                            self._log(f"    ✗ not found in {line.split(':')[1]}")
                    if found:
                        deleted += 1
                    else:
                        self._log(f"    ✗ file does not exist on server — nothing removed")
            self._log(f"\n✓ Done — {deleted}/{len(self.delete_files)} photo(s) removed")
            self.after(0, self._delete_complete)
        except Exception as e:
            self._log(f"\n✗ Delete failed: {e}")
            self.after(0, self._delete_failed)

    def _delete_complete(self):
        self.processing = False
        self.del_exec_btn.config(text="DELETE FROM SERVER", fg=WHITE, cursor="hand2")
        self._clear_delete_queue()
        self._log("✓ All deletions complete.")

    def _delete_failed(self):
        self.processing = False
        self.del_exec_btn.config(text="DELETE FROM SERVER", fg=WHITE, cursor="hand2")
        self._log("✗ Delete operation failed. Check log above.")


if __name__ == "__main__":
    app = PhotoUploaderApp()
    app.mainloop()
