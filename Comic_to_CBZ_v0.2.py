import os
import re
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

APP_VERSION = "v0.2"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
ARCHIVE_EXTS = {".zip", ".cbz"}


def natural_key(value):
    """Natural sort: 1, 2, 10 instead of 1, 10, 2."""
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", str(value))
    ]


def safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(".")
    return name or "Comic"


def unique_output_path(output_dir, base_name):
    """Avoid overwriting when different sources have the same name."""
    base_name = safe_name(base_name)
    target = output_dir / f"{base_name}.cbz"
    index = 2

    while target.exists():
        target = output_dir / f"{base_name}_{index}.cbz"
        index += 1

    return target


def image_files(folder):
    files = []

    for root, dirs, names in os.walk(folder):
        dirs.sort(key=natural_key)

        for name in names:
            path = Path(root) / name

            if path.suffix.lower() in IMAGE_EXTS:
                files.append(path)

    return sorted(
        files,
        key=lambda p: natural_key(str(p.relative_to(folder)))
    )


def selected_image_files(files):
    return sorted(
        [Path(p) for p in files if Path(p).suffix.lower() in IMAGE_EXTS],
        key=lambda p: natural_key(str(p))
    )


def archive_images(archive):
    with zipfile.ZipFile(archive, "r") as zf:
        names = [
            n for n in zf.namelist()
            if not n.endswith("/")
            and Path(n).suffix.lower() in IMAGE_EXTS
        ]

    return sorted(names, key=natural_key)


def write_cbz_from_folder(folder, output):
    files = image_files(folder)

    if not files:
        return 0, "跳过（没有找到图片）"

    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1
    ) as zf:

        for path in files:
            zf.write(
                path,
                arcname=path.relative_to(folder).as_posix()
            )

    return len(files), "完成"


def write_cbz_from_files(files, output):
    files = selected_image_files(files)

    if not files:
        return 0, "跳过（选择的文件中没有图片）"

    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1
    ) as zf:

        used_names = set()

        for index, path in enumerate(files, start=1):
            # For directly selected images, use natural order and avoid
            # duplicate filenames by adding a numeric suffix.
            filename = path.name

            if filename in used_names:
                stem = path.stem
                suffix = path.suffix
                n = 2

                while f"{stem}_{n}{suffix}" in used_names:
                    n += 1

                filename = f"{stem}_{n}{suffix}"

            used_names.add(filename)

            zf.write(path, arcname=filename)

    return len(files), "完成"


def write_cbz_from_archive(archive, output):
    with zipfile.ZipFile(archive, "r") as src:
        names = [
            n for n in src.namelist()
            if not n.endswith("/")
            and Path(n).suffix.lower() in IMAGE_EXTS
        ]

        names.sort(key=natural_key)

        if not names:
            return 0, "跳过（压缩包中没有找到图片）"

        used_names = set()

        with zipfile.ZipFile(
            output,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=1
        ) as dst_zip:

            for name in names:
                base = Path(name).name
                candidate = base
                index = 2

                while candidate in used_names:
                    candidate = (
                        f"{Path(base).stem}_{index}"
                        f"{Path(base).suffix}"
                    )
                    index += 1

                used_names.add(candidate)
                dst_zip.writestr(candidate, src.read(name))

    return len(names), "完成"


class App:
    def __init__(self, root):
        self.root = root

        root.title(f"漫画批量转 CBZ {APP_VERSION}")
        root.geometry("900x650")
        root.minsize(760, 520)

        self.sources = []
        self.source_display = tk.StringVar(value="尚未添加来源")
        self.output = tk.StringVar()
        self.status = tk.StringVar(
            value="可以添加多个文件，也可以连续添加多个文件夹。"
        )

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)

        # ---------------- Source ----------------
        ttk.Label(
            main,
            text="转换来源",
            font=("Microsoft YaHei UI", 11, "bold")
        ).pack(anchor="w")

        ttk.Label(
            main,
            text="支持：多选 ZIP/CBZ、图片文件；多个文件夹可连续添加。"
        ).pack(anchor="w", pady=(2, 8))

        button_row = ttk.Frame(main)
        button_row.pack(fill="x", pady=(0, 8))

        ttk.Button(
            button_row,
            text="添加文件（可多选）",
            command=self.add_files
        ).pack(side="left")

        ttk.Button(
            button_row,
            text="添加文件夹",
            command=self.add_folder
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_row,
            text="清空列表",
            command=self.clear_sources
        ).pack(side="left", padx=(8, 0))

        ttk.Button(
            button_row,
            text="移除选中",
            command=self.remove_selected
        ).pack(side="left", padx=(8, 0))

        # ---------------- Source list ----------------
        list_frame = ttk.Frame(main)
        list_frame.pack(fill="both", expand=False)

        columns = ("type", "path")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            height=10,
            selectmode="extended"
        )

        self.tree.heading("type", text="类型")
        self.tree.heading("path", text="来源")

        self.tree.column("type", width=90, anchor="center")
        self.tree.column("path", width=650)

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.tree.yview
        )

        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ---------------- Output ----------------
        ttk.Label(
            main,
            text="输出目录",
            font=("Microsoft YaHei UI", 11, "bold")
        ).pack(anchor="w", pady=(16, 5))

        output_row = ttk.Frame(main)
        output_row.pack(fill="x")

        ttk.Entry(
            output_row,
            textvariable=self.output
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            output_row,
            text="选择…",
            command=self.pick_output
        ).pack(side="left", padx=(8, 0))

        # ---------------- Options ----------------
        options = ttk.Frame(main)
        options.pack(fill="x", pady=(12, 8))

        self.overwrite = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            options,
            text="覆盖同名 CBZ（关闭时自动生成 _2、_3…，不会覆盖已有文件）",
            variable=self.overwrite
        ).pack(anchor="w")

        # ---------------- Log ----------------
        ttk.Label(
            main,
            text="处理日志",
            font=("Microsoft YaHei UI", 11, "bold")
        ).pack(anchor="w", pady=(10, 5))

        self.log = tk.Text(
            main,
            height=11,
            wrap="word",
            state="disabled"
        )

        self.log.pack(fill="both", expand=True)

        # ---------------- Bottom ----------------
        bottom = ttk.Frame(main)
        bottom.pack(fill="x", pady=(8, 0))

        ttk.Label(
            bottom,
            textvariable=self.status
        ).pack(side="left")

        self.run_btn = ttk.Button(
            bottom,
            text="开始批量转换",
            command=self.run
        )

        self.run_btn.pack(side="right")

    # --------------------------------------------------
    # Source management
    # --------------------------------------------------

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择漫画文件（可多选）",
            filetypes=[
                (
                    "漫画文件",
                    "*.zip *.cbz *.jpg *.jpeg *.png *.webp *.gif "
                    "*.bmp *.tif *.tiff *.avif"
                ),
                ("ZIP / CBZ", "*.zip *.cbz"),
                ("图片", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tif *.tiff *.avif"),
                ("所有文件", "*.*")
            ]
        )

        if not paths:
            return

        added = 0

        for path in paths:
            path = Path(path)

            if path.suffix.lower() not in IMAGE_EXTS | ARCHIVE_EXTS:
                self.log_line(f"忽略不支持的文件：{path}")
                continue

            if self.add_source("file", path):
                added += 1

        self.update_status_after_add(added)

    def add_folder(self):
        """
        tkinter's standard directory picker does not provide native
        multi-folder selection on Windows.

        Therefore this button uses a continuous selection flow:
        select a folder -> automatically ask whether to add another.
        This still allows an arbitrary number of folders to be added
        in one operation.
        """
        added = 0

        while True:
            path = filedialog.askdirectory(
                title="选择漫画文件夹（取消即可结束添加）",
                mustexist=True
            )

            if not path:
                break

            path = Path(path)

            if self.add_source("folder", path):
                added += 1

            again = messagebox.askyesno(
                "继续添加文件夹？",
                "文件夹已添加。\n\n是否继续添加另一个文件夹？"
            )

            if not again:
                break

        self.update_status_after_add(added)

    def add_source(self, source_type, path):
        path = Path(path).resolve()

        for existing_type, existing_path in self.sources:
            if existing_path == path:
                return False

        self.sources.append((source_type, path))

        if source_type == "folder":
            type_name = "文件夹"
        elif path.suffix.lower() in ARCHIVE_EXTS:
            type_name = "压缩包"
        else:
            type_name = "图片"

        self.tree.insert(
            "",
            "end",
            values=(type_name, str(path))
        )

        return True

    def remove_selected(self):
        selected = self.tree.selection()

        if not selected:
            return

        indexes = []

        for item_id in selected:
            indexes.append(self.tree.index(item_id))

        for item_id in selected:
            self.tree.delete(item_id)

        for index in sorted(indexes, reverse=True):
            del self.sources[index]

        self.status.set(f"当前共有 {len(self.sources)} 个来源。")

    def clear_sources(self):
        self.sources.clear()

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.status.set("来源列表已清空。")

    # --------------------------------------------------
    # UI helpers
    # --------------------------------------------------

    def pick_output(self):
        value = filedialog.askdirectory(
            title="选择 CBZ 输出目录"
        )

        if value:
            self.output.set(value)

    def update_status_after_add(self, added):
        if added:
            self.status.set(
                f"已添加 {added} 个来源，当前共 {len(self.sources)} 个来源。"
            )

    def log_line(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.root.update_idletasks()

    # --------------------------------------------------
    # Conversion
    # --------------------------------------------------

    def get_output_path(self, base_name):
        out_dir = Path(self.output.get()).expanduser()

        if self.overwrite.get():
            return out_dir / f"{safe_name(base_name)}.cbz"

        return unique_output_path(
            out_dir,
            base_name
        )

    def run(self):
        if not self.sources:
            messagebox.showwarning(
                "没有转换来源",
                "请先添加至少一个文件或文件夹。"
            )
            return

        if not self.output.get().strip():
            messagebox.showwarning(
                "没有输出目录",
                "请先选择 CBZ 输出目录。"
            )
            return

        output_dir = Path(self.output.get()).expanduser()

        try:
            output_dir.mkdir(
                parents=True,
                exist_ok=True
            )
        except Exception as e:
            messagebox.showerror(
                "无法创建输出目录",
                str(e)
            )
            return

        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        self.run_btn.configure(state="disabled")

        success = 0
        skipped = 0
        errors = 0

        # Group directly selected image files into one CBZ.
        selected_images = [
            path
            for source_type, path in self.sources
            if source_type == "file"
            and path.suffix.lower() in IMAGE_EXTS
        ]

        # Process folders and archives individually.
        individual_sources = [
            (source_type, path)
            for source_type, path in self.sources
            if not (
                source_type == "file"
                and path.suffix.lower() in IMAGE_EXTS
            )
        ]

        try:
            # ------------------------------------------
            # 1. Folders / ZIP / CBZ
            # ------------------------------------------
            for source_type, source in individual_sources:
                base_name = source.name

                if source_type == "folder":
                    target = self.get_output_path(base_name)

                    try:
                        count, result = write_cbz_from_folder(
                            source,
                            target
                        )

                    except Exception as e:
                        errors += 1
                        self.log_line(
                            f"失败：{source}；原因：{e}"
                        )
                        continue

                else:
                    target = self.get_output_path(
                        source.stem
                    )

                    try:
                        count, result = write_cbz_from_archive(
                            source,
                            target
                        )

                    except zipfile.BadZipFile:
                        errors += 1
                        self.log_line(
                            f"失败：{source.name} 不是有效的 ZIP/CBZ 文件。"
                        )
                        continue

                    except Exception as e:
                        errors += 1
                        self.log_line(
                            f"失败：{source}；原因：{e}"
                        )
                        continue

                if count:
                    success += 1
                    self.log_line(
                        f"完成：{source.name} → "
                        f"{target.name}（{count} 张图片）"
                    )
                else:
                    skipped += 1

                    if target.exists():
                        try:
                            target.unlink()
                        except OSError:
                            pass

                    self.log_line(
                        f"{result}：{source.name}"
                    )

            # ------------------------------------------
            # 2. Directly selected images
            # ------------------------------------------
            if selected_images:
                base_name = "合并图片"

                # If there are no folders/archives and all selected
                # images share one parent folder, use that folder name.
                parents = {
                    path.parent.resolve()
                    for path in selected_images
                }

                if len(parents) == 1:
                    base_name = next(
                        iter(parents)
                    ).name

                target = self.get_output_path(base_name)

                try:
                    count, result = write_cbz_from_files(
                        selected_images,
                        target
                    )

                    if count:
                        success += 1
                        self.log_line(
                            f"完成：选中的 {len(selected_images)} 个图片"
                            f" → {target.name}"
                            f"（{count} 张图片）"
                        )
                    else:
                        skipped += 1
                        self.log_line(
                            f"{result}"
                        )

                except Exception as e:
                    errors += 1
                    self.log_line(
                        f"图片批量处理失败：{e}"
                    )

        finally:
            self.run_btn.configure(state="normal")

        self.status.set(
            f"处理结束：成功 {success}，跳过 {skipped}，失败 {errors}"
        )

        messagebox.showinfo(
            "处理完成",
            self.status.get()
        )


if __name__ == "__main__":
    root = tk.Tk()

    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass

    App(root)
    root.mainloop()
