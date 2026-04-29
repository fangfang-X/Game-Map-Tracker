"""Batch convert .json and .txt files by changing only their suffix.

The converter intentionally copies bytes without parsing or rewriting file
contents. This keeps route/config files intact even when the source text is not
valid JSON.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


MODE_JSON_TO_TXT = "json_to_txt"
MODE_TXT_TO_JSON = "txt_to_json"
MODE_AUTO = "auto"
MODES = {MODE_JSON_TO_TXT, MODE_TXT_TO_JSON, MODE_AUTO}


@dataclass
class ConversionReport:
    converted: int = 0
    skipped: int = 0
    ignored: int = 0
    errors: int = 0
    messages: list[str] = field(default_factory=list)


def target_suffix_for(path: Path, mode: str) -> str | None:
    """Return the converted suffix for path, or None when it should be ignored."""
    suffix = path.suffix.lower()
    if mode == MODE_JSON_TO_TXT:
        return ".txt" if suffix == ".json" else None
    if mode == MODE_TXT_TO_JSON:
        return ".json" if suffix == ".txt" else None
    if mode == MODE_AUTO:
        if suffix == ".json":
            return ".txt"
        if suffix == ".txt":
            return ".json"
        return None
    raise ValueError(f"Unsupported conversion mode: {mode}")


def iter_source_files(input_dir: Path, recursive: bool = True) -> Iterable[Path]:
    if recursive:
        yield from (path for path in sorted(input_dir.rglob("*")) if path.is_file())
        return
    yield from (path for path in sorted(input_dir.iterdir()) if path.is_file())


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _same_directory(left: Path, right: Path) -> bool:
    return _resolved(left) == _resolved(right)


def convert_files(
    input_dir: str | Path,
    output_dir: str | Path,
    mode: str = MODE_JSON_TO_TXT,
    *,
    recursive: bool = True,
    overwrite: bool = False,
) -> ConversionReport:
    """Convert matching files from input_dir into output_dir.

    The source files are never edited. Matching files are copied byte-for-byte
    and only the output filename suffix changes.
    """
    if mode not in MODES:
        raise ValueError(f"Unsupported conversion mode: {mode}")

    source_root = Path(input_dir).expanduser()
    target_root = Path(output_dir).expanduser()
    if _same_directory(source_root, target_root):
        raise ValueError("输入目录和输出目录不能相同。")
    if not source_root.is_dir():
        raise ValueError(f"输入目录不存在：{source_root}")

    report = ConversionReport()
    source_files = list(iter_source_files(source_root, recursive=recursive))
    target_root.mkdir(parents=True, exist_ok=True)

    for source in source_files:
        target_suffix = target_suffix_for(source, mode)
        if target_suffix is None:
            report.ignored += 1
            continue

        relative = source.relative_to(source_root)
        target = target_root / relative.with_suffix(target_suffix)

        if target.exists() and not overwrite:
            report.skipped += 1
            report.messages.append(f"[跳过] 已存在：{target}")
            continue

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        except Exception as exc:
            report.errors += 1
            report.messages.append(f"[错误] {source} -> {target}: {exc}")
            continue

        report.converted += 1
        report.messages.append(f"[完成] {source} -> {target}")

    return report


def _mode_label(mode: str) -> str:
    labels = {
        MODE_JSON_TO_TXT: ".json -> .txt",
        MODE_TXT_TO_JSON: ".txt -> .json",
        MODE_AUTO: "自动互转：.json <-> .txt",
    }
    return labels.get(mode, mode)


def _run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("JSON/TXT 批量改后缀工具")
    root.geometry("760x520")
    root.minsize(680, 440)

    input_var = tk.StringVar()
    output_var = tk.StringVar()
    mode_var = tk.StringVar(value=MODE_JSON_TO_TXT)
    recursive_var = tk.BooleanVar(value=True)
    overwrite_var = tk.BooleanVar(value=False)

    def browse_input() -> None:
        selected = filedialog.askdirectory(title="选择输入目录")
        if selected:
            input_var.set(selected)

    def browse_output() -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            output_var.set(selected)

    def append_log(text: str) -> None:
        log_text.configure(state="normal")
        log_text.insert("end", text + "\n")
        log_text.see("end")
        log_text.configure(state="disabled")

    def clear_log() -> None:
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")

    def start_conversion() -> None:
        clear_log()
        input_path = input_var.get().strip()
        output_path = output_var.get().strip()
        if not input_path or not output_path:
            messagebox.showwarning("缺少目录", "请先选择输入目录和输出目录。")
            return

        start_button.configure(state="disabled")
        root.update_idletasks()
        try:
            report = convert_files(
                input_path,
                output_path,
                mode_var.get(),
                recursive=recursive_var.get(),
                overwrite=overwrite_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("转换失败", str(exc))
            append_log(f"[错误] {exc}")
            return
        finally:
            start_button.configure(state="normal")

        append_log(f"转换模式：{_mode_label(mode_var.get())}")
        append_log(f"已转换：{report.converted}")
        append_log(f"已跳过：{report.skipped}")
        append_log(f"已忽略：{report.ignored}")
        append_log(f"错误数：{report.errors}")
        if report.messages:
            append_log("")
            for message in report.messages:
                append_log(message)

        if report.errors:
            messagebox.showwarning("转换完成但有错误", "转换已结束，但存在错误。请查看日志。")
        else:
            messagebox.showinfo("转换完成", "转换已完成。")

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(1, weight=1)
    outer.rowconfigure(5, weight=1)

    ttk.Label(outer, text="输入目录").grid(row=0, column=0, sticky="w", pady=(0, 8))
    ttk.Entry(outer, textvariable=input_var).grid(row=0, column=1, sticky="ew", padx=(10, 10), pady=(0, 8))
    ttk.Button(outer, text="浏览...", command=browse_input).grid(row=0, column=2, sticky="ew", pady=(0, 8))

    ttk.Label(outer, text="输出目录").grid(row=1, column=0, sticky="w", pady=(0, 8))
    ttk.Entry(outer, textvariable=output_var).grid(row=1, column=1, sticky="ew", padx=(10, 10), pady=(0, 8))
    ttk.Button(outer, text="浏览...", command=browse_output).grid(row=1, column=2, sticky="ew", pady=(0, 8))

    mode_frame = ttk.LabelFrame(outer, text="转换方向", padding=10)
    mode_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 10))
    mode_frame.columnconfigure(0, weight=1)
    mode_frame.columnconfigure(1, weight=1)
    mode_frame.columnconfigure(2, weight=1)
    ttk.Radiobutton(mode_frame, text=".json -> .txt", value=MODE_JSON_TO_TXT, variable=mode_var).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Radiobutton(mode_frame, text=".txt -> .json", value=MODE_TXT_TO_JSON, variable=mode_var).grid(
        row=0, column=1, sticky="w"
    )
    ttk.Radiobutton(mode_frame, text="自动互转", value=MODE_AUTO, variable=mode_var).grid(
        row=0, column=2, sticky="w"
    )

    option_frame = ttk.Frame(outer)
    option_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 12))
    ttk.Checkbutton(option_frame, text="包含子文件夹", variable=recursive_var).pack(side="left")
    ttk.Checkbutton(option_frame, text="覆盖已存在文件", variable=overwrite_var).pack(side="left", padx=(20, 0))

    start_button = ttk.Button(outer, text="开始转换", command=start_conversion)
    start_button.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 12))

    log_text = tk.Text(outer, height=12, wrap="none", state="disabled")
    log_text.grid(row=5, column=0, columnspan=3, sticky="nsew")
    y_scroll = ttk.Scrollbar(outer, orient="vertical", command=log_text.yview)
    y_scroll.grid(row=5, column=3, sticky="ns")
    log_text.configure(yscrollcommand=y_scroll.set)

    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch convert .json and .txt files by changing only suffixes.")
    parser.add_argument("--input", help="Input folder")
    parser.add_argument("--output", help="Output folder")
    parser.add_argument("--mode", choices=sorted(MODES), default=MODE_JSON_TO_TXT)
    parser.add_argument("--no-recursive", action="store_true", help="Only convert files directly in the input folder")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--gui", action="store_true", help="Open the graphical interface")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.gui or not args.input or not args.output:
        return _run_gui()

    try:
        report = convert_files(
            args.input,
            args.output,
            args.mode,
            recursive=not args.no_recursive,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Mode: {_mode_label(args.mode)}")
    print(f"Converted: {report.converted}")
    print(f"Skipped: {report.skipped}")
    print(f"Ignored: {report.ignored}")
    print(f"Errors: {report.errors}")
    for message in report.messages:
        print(message)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
