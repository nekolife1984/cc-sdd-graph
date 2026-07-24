#!/usr/bin/env python3
'extract_tags.py — コードから @impl/@module/@feature タグ、'
DOCSTRING = """extract_tags.py - コードから @impl/@module/@feature タグ、仕様書から @spec/@design/@satisfies タグを抽出する。

Usage:
  python3 .agents/scripts/extract_tags.py --dir strands-chat/
  python3 .agents/scripts/extract_tags.py --file strands-chat/agency/engine.py
  python3 .agents/scripts/extract_tags.py --dir strands-chat/ --format json
  python3 .agents/scripts/extract_tags.py --dir strands-chat/ --check-missing

対応タグ:
  コード:  # @impl 1.1    # @module auth    # @feature login
  仕様書:  <!-- @spec 1.1 -->  <!-- @design AuthService -->  <!-- @satisfies 1.1, 1.2 -->

オプション:
  --dir <path>       再帰的にスキャンするディレクトリ
  --file <path>      単一ファイルをスキャン
  --format text|json 出力形式（デフォルト: text）
  --check-missing    要件タグなしのPythonファイルを警告（exit 1 で終了）
  --trace-mapping    出力を .trace-mapping.yaml 形式で表示
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Optional


# 対応ファイル拡張子
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift", ".md"}

# タグパターン: # @impl 1.1, 1.2 | # @module auth | # @feature login
# HTMLコメント: <!-- @spec 1 --> <!-- @design Auth --> <!-- @satisfies 1.1, 1.2 -->
TAG_RE = re.compile(
    r"(?:#\s*@(?P<tag>impl|module|feature)\s+(?P<value>.+?)(?:\s*$|#))|"
    r"(?:<!--\s*@(?P<mdtag>spec|design|satisfies)\s+(?P<mdvalue>.+?)\s*-->)",
    re.MULTILINE,
)


def extract_tags_from_file(filepath: Path) -> list[dict]:
    """ファイルから全てのタグを抽出する。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    tags = []
    for match in TAG_RE.finditer(content):
        # コードタグ: # @impl, # @module, # @feature
        tag_type = match.group("tag")
        if tag_type:
            value = match.group("value").strip().rstrip(",")
            tags.append({
                "file": str(filepath),
                "tag": tag_type,
                "value": value,
            })
        # Markdown HTMLコメントタグ: <!-- @spec, @design, @satisfies -->
        md_tag = match.group("mdtag")
        if md_tag:
            md_value = match.group("mdvalue").strip().rstrip(",")
            tags.append({
                "file": str(filepath),
                "tag": md_tag,
                "value": md_value,
            })
    return tags


def scan_directory(directory: Path) -> list[dict]:
    """ディレクトリを再帰的にスキャンする。"""
    all_tags = []
    for ext in EXTENSIONS:
        for fpath in directory.rglob(f"*{ext}"):
            # __pycache__, .venv, node_modules, .git をスキップ
            if any(part.startswith("__") or part in (".venv", "node_modules", ".git", "dist", "build") for part in fpath.parts):
                continue
            all_tags.extend(extract_tags_from_file(fpath))
    return all_tags


def get_files_without_tags(directory: Path) -> list[Path]:
    """タグが1つもないソースファイルをリストする。"""
    untagged = []
    for ext in EXTENSIONS:
        for fpath in directory.rglob(f"*{ext}"):
            if any(part.startswith("__") or part in (".venv", "node_modules", ".git", "dist", "build") for part in fpath.parts):
                continue
            tags = extract_tags_from_file(fpath)
            if not tags:
                untagged.append(fpath)
    return untagged


def format_text(tags: list[dict]) -> str:
    """テキスト形式で出力する。"""
    lines = []
    current_file = None
    for t in sorted(tags, key=lambda x: x["file"]):
        if t["file"] != current_file:
            if current_file:
                lines.append("")
            current_file = t["file"]
            lines.append(f"# {current_file}")
        lines.append(f"  @{t['tag']} {t['value']}")
    return "\n".join(lines)


def format_trace_mapping(tags: list[dict]) -> str:
    """.trace-mapping.yaml に追記可能な形式で出力する。"""
    lines = []
    # impl タグをファイルごとに集約
    impl_by_file: dict[str, list[str]] = {}
    module_by_file: dict[str, set[str]] = {}
    feature_by_file: dict[str, set[str]] = {}

    for t in tags:
        f = t["file"]
        if t["tag"] == "impl":
            impl_by_file.setdefault(f, [])
            impl_by_file[f].extend(v.strip() for v in t["value"].split(","))
        elif t["tag"] == "module":
            module_by_file.setdefault(f, set())
            module_by_file[f].add(t["value"].strip())
        elif t["tag"] == "feature":
            feature_by_file.setdefault(f, set())
            feature_by_file[f].add(t["value"].strip())

    lines.append("# 以下は extract_tags.py の出力です。")
    lines.append("# .trace-mapping.yaml にコピーして使用してください。\n")

    for filepath, impl_ids in sorted(impl_by_file.items()):
        modules = module_by_file.get(filepath, set())
        features = feature_by_file.get(filepath, set())
        lines.append(f"# file: {filepath}")
        if modules:
            lines.append(f"# module: {', '.join(sorted(modules))}")
        if features:
            lines.append(f"# feature: {', '.join(sorted(features))}")
        for impl_id in impl_ids:
            impl_id = impl_id.strip()
            if impl_id:
                lines.append(f"  # ← @impl {impl_id} のエントリを追加")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="コードから @impl/@module/@feature タグ、仕様書から @spec/@design/@satisfies タグを抽出")
    parser.add_argument("--dir", type=str, help="再帰的にスキャンするディレクトリ")
    parser.add_argument("--file", type=str, help="単一ファイルをスキャン")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="出力形式")
    parser.add_argument("--check-missing", action="store_true", help="タグのないファイルを警告")
    parser.add_argument("--trace-mapping", action="store_true", help=".trace-mapping.yaml 追記形式で出力")
    args = parser.parse_args()

    if not args.dir and not args.file:
        # デフォルト: カレントディレクトリをスキャン
        args.dir = "."

    tags: list[dict] = []
    if args.file:
        tags = extract_tags_from_file(Path(args.file))
    elif args.dir:
        tags = scan_directory(Path(args.dir))

    if args.check_missing:
        target = Path(args.dir or ".")
        untagged = get_files_without_tags(target)
        if untagged:
            print(f"WARNING: {len(untagged)} file(s) without @impl/@module/@feature tags:")
            for f in untagged:
                print(f"  {f}")
            sys.exit(1)
        print(f"OK: All {len(set(t['file'] for t in tags))} tagged files have tags.")
        sys.exit(0)

    if args.format == "json":
        import json
        print(json.dumps(tags, indent=2))
    elif args.trace_mapping:
        print(format_trace_mapping(tags))
    else:
        print(format_text(tags))


if __name__ == "__main__":
    main()
