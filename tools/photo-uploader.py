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
REMOTE_WEB_DIR   = "/var/www/html/michaelbesaw.com/photos/"
REMOTE_MOBILE_DIR= "/var/www/html/michaelbesaw.com/photos-mobile/"
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

# ── Colors ────────────────────────────────────────────────────────────────────
BG       = "#0c0c0b"
SURFACE  = "#161614"
BORDER   = "#2a2a28"
TEXT     = "#e8e0d0"
MUTED    = "#7a7468"
ACCENT   = "#c8b89a"
SUCCESS  = "#6a9a6a"
ERROR    = "#a06060"
# ─────────────────────────────────────────────────────────────────────────────


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
            # Too small, bump quality back up a notch
            q = min(quality, q + 5)
            kwargs["quality"] = q
            if exif_bytes:
                kwargs["exif"] = exif_bytes
            img.save(path, **kwargs)
        break
    return os.path.getsize(path)


def process_photo(src_path, web_dir, mobile_dir):
    """Process one photo into web and mobile versions. Returns (web_path, mobile_path, info_dict)."""
    src = Path(src_path)
    out_name = src.stem + ".jpg"
    web_out = web_dir / out_name
    mobile_out = mobile_dir / out_name

    with Image.open(src) as img:
        img = to_rgb(img)
        exif_bytes = get_exif(img)

        # Web version
        web_img = resize_image(img, WEB_MAX_DIM)
        web_size = save_jpeg(web_img, web_out, exif_bytes, WEB_QUALITY, WEB_MIN_KB, WEB_MAX_KB)

        # Mobile version
        mob_img = resize_image(img, MOBILE_MAX_DIM)
        mob_size = save_jpeg(mob_img, mobile_out, exif_bytes, MOBILE_QUALITY, max_kb=MOBILE_MAX_KB)

    info = {
        "original_kb": os.path.getsize(src) / 1024,
        "web_kb": web_size / 1024,
        "mobile_kb": mob_size / 1024,
        "web_dim": web_img.size,
        "mobile_dim": mob_img.size,
    }
    return web_out, mobile_out, info


class PhotoUploaderApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("michaelbesaw — photo uploader")
        self.configure(bg=BG)
        self.geometry("700x780")
        self.resizable(True, True)
        self.minsize(600, 650)

        self.queued_files = []   # list of Path objects
        self.delete_files = []   # list of filenames to delete from server
        self.processing = False

        self._build_ui()

    def _make_btn(self, parent, text, command, side="left"):
        """Custom label-based button that stays fully dark."""
        f = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        lbl = tk.Label(f, text=text, font=("Courier New", 10),
                       bg=SURFACE, fg=MUTED, padx=16, pady=8, cursor="hand2")
        lbl.pack()
        f.pack(side=side, padx=(0, 8) if side == "left" else (8, 0))

        def on_enter(e): lbl.config(bg=BORDER, fg=TEXT)
        def on_leave(e): lbl.config(bg=SURFACE, fg=MUTED if lbl.cget("state") != "disabled" else "#3a3a38")
        def on_press(e):
            if lbl.cget("state") != "disabled":
                command()

        lbl.bind("<Enter>", on_enter)
        lbl.bind("<Leave>", on_leave)
        lbl.bind("<Button-1>", on_press)
        lbl._frame = f
        return lbl

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(hdr, text="michaelbesaw", font=("Courier New", 13), bg=BG, fg=MUTED).pack(side="left")
        tk.Label(hdr, text=" / photo uploader", font=("Courier New", 13), bg=BG, fg="#3a3a38").pack(side="left")

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x", padx=24, pady=(12, 0))

        # ── Drop zone ──
        drop_frame = tk.Frame(self, bg=SURFACE, bd=0, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=BORDER)
        drop_frame.pack(fill="x", padx=24, pady=16)

        self.drop_label = tk.Label(
            drop_frame,
            text="drag photos here  ·  click to browse",
            font=("Courier New", 11),
            bg=SURFACE, fg="#3a3a38",
            pady=26, padx=20,
            justify="center",
            cursor="hand2"
        )
        self.drop_label.pack(fill="x")

        def drop_enter(e): self.drop_label.config(fg=MUTED)
        def drop_leave(e): self.drop_label.config(fg="#3a3a38")

        drop_frame.drop_target_register(DND_FILES)
        drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_label.drop_target_register(DND_FILES)
        self.drop_label.dnd_bind("<<Drop>>", self._on_drop)
        self.drop_label.bind("<Enter>", drop_enter)
        self.drop_label.bind("<Leave>", drop_leave)
        drop_frame.bind("<Button-1>", self._browse_files)
        self.drop_label.bind("<Button-1>", self._browse_files)

        # ── File list ──
        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=24)

        list_header = tk.Frame(list_frame, bg=BG)
        list_header.pack(fill="x", pady=(0, 6))
        tk.Label(list_header, text="QUEUED", font=("Courier New", 9),
                 bg=BG, fg="#3a3a38").pack(side="left")
        self.count_label = tk.Label(list_header, text="0 files",
                                    font=("Courier New", 9), bg=BG, fg="#3a3a38")
        self.count_label.pack(side="right")

        lb_frame = tk.Frame(list_frame, bg=SURFACE, highlightthickness=1,
                            highlightbackground=BORDER)
        lb_frame.pack(fill="both", expand=True)

        self.file_listbox = tk.Listbox(
            lb_frame,
            bg=SURFACE, fg=MUTED,
            selectbackground="#222220",
            selectforeground=TEXT,
            font=("Courier New", 11),
            borderwidth=0, highlightthickness=0,
            activestyle="none",
        )
        self.file_listbox.pack(fill="both", expand=True, padx=10, pady=6)

        # Mouse wheel scroll (no scrollbar)
        self.file_listbox.bind("<MouseWheel>", lambda e: self.file_listbox.yview_scroll(-1*(e.delta//120), "units"))
        self.file_listbox.bind("<Button-4>", lambda e: self.file_listbox.yview_scroll(-1, "units"))
        self.file_listbox.bind("<Button-5>", lambda e: self.file_listbox.yview_scroll(1, "units"))
        self.file_listbox.bind("<Button-2>", self._remove_selected)
        self.file_listbox.bind("<Delete>", self._remove_selected)

        # ── Log output ──
        log_header = tk.Frame(self, bg=BG)
        log_header.pack(fill="x", padx=24, pady=(10, 4))
        tk.Label(log_header, text="LOG", font=("Courier New", 9),
                 bg=BG, fg="#3a3a38").pack(side="left")

        log_frame = tk.Frame(self, bg=SURFACE, highlightthickness=1,
                             highlightbackground=BORDER)
        log_frame.pack(fill="x", padx=24)

        self.log_text = tk.Text(
            log_frame,
            height=6,
            bg=SURFACE, fg="#3a3a38",
            insertbackground=SURFACE,
            font=("Courier New", 10),
            borderwidth=0, highlightthickness=0,
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(fill="x", padx=10, pady=6)

        # Mouse wheel scroll on log
        self.log_text.bind("<MouseWheel>", lambda e: self.log_text.yview_scroll(-1*(e.delta//120), "units"))
        self.log_text.bind("<Button-4>", lambda e: self.log_text.yview_scroll(-1, "units"))
        self.log_text.bind("<Button-5>", lambda e: self.log_text.yview_scroll(1, "units"))

        # ── Buttons ──
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=(12, 20))

        self.clear_btn  = self._make_btn(btn_frame, "CLEAR", self._clear_queue, side="left")
        self.upload_btn = self._make_btn(btn_frame, "PROCESS + UPLOAD", self._start_upload, side="right")

        # Progress bar — thin canvas-drawn line, no native widget
        self.progress_canvas = tk.Canvas(btn_frame, height=2, bg=BG,
                                         highlightthickness=0, bd=0)
        self._progress_active = False
        self._progress_pos = 0

        # ── Delete from server section ──
        sep2 = tk.Frame(self, bg=BORDER, height=1)
        sep2.pack(fill="x", padx=24, pady=(0, 12))

        del_header = tk.Frame(self, bg=BG)
        del_header.pack(fill="x", padx=24, pady=(0, 6))
        tk.Label(del_header, text="DELETE FROM SERVER", font=("Courier New", 9),
                 bg=BG, fg="#3a3a38").pack(side="left")
        self.del_count_label = tk.Label(del_header, text="0 files",
                                         font=("Courier New", 9), bg=BG, fg="#3a3a38")
        self.del_count_label.pack(side="right")

        # Filename entry row
        entry_frame = tk.Frame(self, bg=BG)
        entry_frame.pack(fill="x", padx=24, pady=(0, 6))

        self.del_entry = tk.Entry(
            entry_frame,
            bg=SURFACE, fg=TEXT,
            insertbackground=TEXT,
            font=("Courier New", 11),
            borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=MUTED,
        )
        self.del_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.del_entry.insert(0, "")
        self._del_placeholder = True
        self._set_del_placeholder()
        self.del_entry.bind("<FocusIn>", self._del_focus_in)
        self.del_entry.bind("<FocusOut>", self._del_focus_out)
        self.del_entry.bind("<Return>", self._add_delete_file)

        self.del_add_btn = self._make_btn(entry_frame, "ADD", self._add_delete_file, side="right")

        # Delete file list
        del_lb_frame = tk.Frame(self, bg=SURFACE, highlightthickness=1,
                                 highlightbackground=BORDER)
        del_lb_frame.pack(fill="both", expand=True, padx=24, pady=(0, 6))

        self.del_listbox = tk.Listbox(
            del_lb_frame,
            bg=SURFACE, fg=MUTED,
            selectbackground="#222220",
            selectforeground=TEXT,
            font=("Courier New", 11),
            borderwidth=0, highlightthickness=0,
            activestyle="none",
            height=4,
        )
        self.del_listbox.pack(fill="both", expand=True, padx=10, pady=6)
        self.del_listbox.bind("<MouseWheel>", lambda e: self.del_listbox.yview_scroll(-1*(e.delta//120), "units"))
        self.del_listbox.bind("<Button-2>", self._remove_delete_selected)
        self.del_listbox.bind("<Delete>", self._remove_delete_selected)

        # Delete buttons
        del_btn_frame = tk.Frame(self, bg=BG)
        del_btn_frame.pack(fill="x", padx=24, pady=(0, 20))

        self.del_clear_btn = self._make_btn(del_btn_frame, "CLEAR", self._clear_delete_queue, side="left")
        self.del_exec_btn = self._make_btn(del_btn_frame, "DELETE FROM SERVER", self._start_delete, side="right")

    def _log(self, msg, color=None):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _on_drop(self, event):
        raw = event.data
        # tkinterdnd2 returns paths wrapped in {} on Mac for paths with spaces
        files = self.tk.splitlist(raw)
        self._add_files(files)

    def _browse_files(self, event=None):
        files = filedialog.askopenfilenames(
            title="Select Photos",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp *.tiff *.bmp"), ("All files", "*.*")]
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

    def _remove_selected(self, event=None):
        selected = self.file_listbox.curselection()
        for i in reversed(selected):
            self.file_listbox.delete(i)
            del self.queued_files[i]
        self.count_label.config(text=f"{len(self.queued_files)} file(s)")

    def _clear_queue(self):
        self.queued_files.clear()
        self.file_listbox.delete(0, "end")
        self.count_label.config(text="0 files")
        self._log("Queue cleared")

    def _start_upload(self):
        if not self.queued_files:
            messagebox.showwarning("No files", "Add photos to the queue first.")
            return
        if self.processing:
            return
        self.processing = True
        self.upload_btn.config(text="PROCESSING...")
        self.upload_btn.config(fg="#3a3a38", cursor="arrow")
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
        self.progress_canvas.create_rectangle(x, 0, x + bar_w, 2, fill=BORDER, outline="")
        self._progress_pos += 4
        self.after(30, self._animate_progress)

    def _process_and_upload(self):
        tmp = Path(tempfile.mkdtemp())
        web_dir = tmp / "photos"
        mobile_dir = tmp / "photos-mobile"
        web_dir.mkdir()
        mobile_dir.mkdir()

        try:
            self._log(f"\nProcessing {len(self.queued_files)} photo(s)...")

            for i, src in enumerate(self.queued_files):
                self._log(f"  [{i+1}/{len(self.queued_files)}] {src.name}")
                try:
                    web_out, mob_out, info = process_photo(src, web_dir, mobile_dir)
                    self._log(
                        f"    web:    {info['web_dim'][0]}×{info['web_dim'][1]}  {info['web_kb']:.0f}KB"
                    )
                    self._log(
                        f"    mobile: {info['mobile_dim'][0]}×{info['mobile_dim'][1]}  {info['mobile_kb']:.0f}KB"
                    )
                except Exception as e:
                    self._log(f"    ERROR: {e}", ERROR)

            self._log("\nUploading web photos...")
            self._rsync(str(web_dir) + "/", f"{RSYNC_USER_HOST}:{REMOTE_WEB_DIR}")

            self._log("Uploading mobile photos...")
            self._rsync(str(mobile_dir) + "/", f"{RSYNC_USER_HOST}:{REMOTE_MOBILE_DIR}")

            self._log(f"\n✓ Done — {len(self.queued_files)} photo(s) uploaded", )
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
        # Log rsync output (files transferred)
        for line in result.stdout.strip().splitlines():
            if line and not line.startswith("sending") and not line.startswith("sent"):
                self._log(f"    {line}")

    def _upload_complete(self):
        self.processing = False
        self._progress_active = False
        self.progress_canvas.pack_forget()
        self.upload_btn.config(text="PROCESS + UPLOAD", fg=MUTED, cursor="hand2")
        self._clear_queue()
        messagebox.showinfo("Done", "Photos processed and uploaded successfully.")

    def _upload_failed(self):
        self.processing = False
        self._progress_active = False
        self.progress_canvas.pack_forget()
        self.upload_btn.config(text="PROCESS + UPLOAD", fg=MUTED, cursor="hand2")
        messagebox.showerror("Upload Failed", "Check the log for details.")

    # ── Delete from server methods ──

    def _set_del_placeholder(self):
        self.del_entry.delete(0, "end")
        self.del_entry.insert(0, "filename.jpg")
        self.del_entry.config(fg="#3a3a38")
        self._del_placeholder = True

    def _del_focus_in(self, event=None):
        if self._del_placeholder:
            self.del_entry.delete(0, "end")
            self.del_entry.config(fg=TEXT)
            self._del_placeholder = False

    def _del_focus_out(self, event=None):
        if not self.del_entry.get().strip():
            self._set_del_placeholder()

    def _add_delete_file(self, event=None):
        name = self.del_entry.get().strip()
        if not name or name == "filename.jpg":
            return
        # Ensure .jpg extension
        if not name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            name += ".jpg"
        if name not in self.delete_files:
            self.delete_files.append(name)
            self.del_listbox.insert("end", name)
        self.del_entry.delete(0, "end")
        self.del_count_label.config(text=f"{len(self.delete_files)} file(s)")

    def _remove_delete_selected(self, event=None):
        selected = self.del_listbox.curselection()
        for i in reversed(selected):
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

        count = len(self.delete_files)
        names = "\n".join(self.delete_files)
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Delete {count} photo(s) from server?\n\n{names}\n\n"
            "This removes from both /photos/ and /photos-mobile/."
        )
        if not confirm:
            return

        self.processing = True
        self.del_exec_btn.config(text="DELETING...", fg="#3a3a38", cursor="arrow")
        threading.Thread(target=self._execute_delete, daemon=True).start()

    def _execute_delete(self):
        try:
            self._log(f"\nDeleting {len(self.delete_files)} photo(s) from server...")

            for name in self.delete_files:
                web_path = REMOTE_WEB_DIR + name
                mobile_path = REMOTE_MOBILE_DIR + name
                rm_cmd = f"rm -f {web_path} {mobile_path}"

                self._log(f"  rm {name}")
                result = subprocess.run(
                    [SSH_CMD, RSYNC_USER_HOST, rm_cmd],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    self._log(f"    ERROR: {result.stderr.strip()}")
                else:
                    self._log(f"    ✓ removed")

            self._log(f"\n✓ Done — {len(self.delete_files)} photo(s) deleted")
            self.after(0, self._delete_complete)

        except Exception as e:
            self._log(f"\n✗ Delete failed: {e}")
            self.after(0, self._delete_failed)

    def _delete_complete(self):
        self.processing = False
        self.del_exec_btn.config(text="DELETE FROM SERVER", fg=MUTED, cursor="hand2")
        self._clear_delete_queue()
        messagebox.showinfo("Done", "Photos deleted from server.")

    def _delete_failed(self):
        self.processing = False
        self.del_exec_btn.config(text="DELETE FROM SERVER", fg=MUTED, cursor="hand2")
        messagebox.showerror("Delete Failed", "Check the log for details.")


if __name__ == "__main__":
    app = PhotoUploaderApp()
    app.mainloop()
