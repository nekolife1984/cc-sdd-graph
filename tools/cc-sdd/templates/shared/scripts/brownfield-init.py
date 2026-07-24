#!/usr/bin/env python3
"""
brownfield-init.py — 既存コードからトレーサビリティを初期化する

既存のコードベース（Brownfieldプロジェクト）をスキャンし、
cc-sdd-graph のトレーサビリティ設定を自動生成する。

Usage:
  # コードをスキャンして .kiro/ + .trace-mapping.yaml を生成
  python3 .agents/scripts/brownfield-init.py

  # ドライラン（変更なし）
  python3 .agents/scripts/brownfield-init.py --dry-run

  # 特定ディレクトリのみスキャン
  python3 .agents/scripts/brownfield-init.py --scan-dir src/

  # 言語を限定
  python3 .agents/scripts/brownfield-init.py --lang py,ts

  # タグ挿入をスキップ（spec生成のみ）
  python3 .agents/scripts/brownfield-init.py --no-tags
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional


# 対応拡張子と言語名
LANG_NAMES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".java": "Java", ".kt": "Kotlin", ".swift": "Swift",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cs": "C#",
}

# @impl タグパターン（# と // の両方）
IMPL_TAG_RE = re.compile(r'(?:#|//)\s*@impl\s+([\d.]+(?:,\s*[\d.]+)*)', re.MULTILINE)

# 関数/クラス定義パターン（言語横断）
FUNC_RE = re.compile(
    r'(?:^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|'
    r'export\s+(?:default\s+)?)?(?:def\s+|function\s+|class\s+|'
    r'fn\s+|pub\s+(?:fn|struct|enum|trait|impl)\s+|'
    r'(?:public\s+|private\s+)?(?:static\s+)?(?:function\s+)?\w+\s*\()|'
    r'^\s*(\w+)\s*=\s*(?:function|lambda|->))'
    r'\s*(\w+)',
    re.MULTILINE,
)

EXCLUDE_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build",
                ".artgraph", ".trace", ".kiro", "bin", "obj", ".vs", "packages",
                "coverage", "htmlcov", ".tox", "vendor", "third_party"}


def detect_modules(project_dir: Path, scan_dirs: list[str],
                   allowed_langs: set[str]) -> dict[str, dict]:
    """コードベースをスキャンしてモジュール構造を検出する。

    Returns:
        {module_name: {
            "files": [rel_paths],
            "funcs": [func_names],
            "langs": {lang: count},
            "imports": [module_names],
        }}
    """
    modules: dict[str, dict] = defaultdict(lambda: {
        "files": [], "funcs": [], "langs": defaultdict(int), "imports": set()
    })

    import_pattern = re.compile(
        r'(?:^from\s+([\w.]+)\s+import|^import\s+([\w.]+)|'
        r'#include\s+[<"](.+?)[>"]|^using\s+([\w.]+);|'
        r'^use\s+([\w:]+))',
        re.MULTILINE,
    )

    for sd in scan_dirs:
        search_path = project_dir / sd if not Path(sd).is_absolute() else Path(sd)
        if not search_path.exists():
            continue
        for ext, lang in LANG_NAMES.items():
            if allowed_langs and lang not in allowed_langs:
                continue
            for fpath in sorted(search_path.rglob(f"*{ext}")):
                if any(part in EXCLUDE_DIRS for part in fpath.parts):
                    continue
                rel = str(fpath.relative_to(project_dir))
                try:
                    content = fpath.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue

                # モジュール名 = 親ディレクトリ名（フラット化）
                parent = fpath.parent.name if fpath.parent != project_dir else "root"
                mod_name = parent if parent and parent != "." else fpath.stem

                modules[mod_name]["files"].append(rel)
                modules[mod_name]["langs"][lang] += 1

                # 関数/クラス抽出
                for match in FUNC_RE.finditer(content):
                    name = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0).split()[-1]
                    if name and len(name) > 1 and not name.startswith("_"):
                        modules[mod_name]["funcs"].append(name)

                # import先から関連モジュールを推定
                for imp_match in import_pattern.finditer(content):
                    imp = next((g for g in imp_match.groups() if g), "")
                    if imp:
                        parts = imp.split(".") if "." in imp else [imp]
                        if parts and parts[0] not in ("os", "sys", "re", "json", "typing",
                                                       "collections", "pathlib", "subprocess"):
                            modules[mod_name]["imports"].add(parts[0])

    # 補完: type hints, set → list
    for mod_data in modules.values():
        mod_data["funcs"] = sorted(set(mod_data["funcs"]))
        mod_data["langs"] = dict(mod_data["langs"])
        mod_data["imports"] = sorted(mod_data["imports"])

    return dict(modules)


def assign_spec_ids(modules: dict[str, dict]) -> dict[str, str]:
    """モジュールに要件IDを割り振る。"""
    return {name: f"{i + 1}.1" for i, name in enumerate(sorted(modules.keys()))}


def generate_requirements(main_module: str, spec_id: str, mod_data: dict) -> str:
    """requirements.md を生成する。"""
    funcs = mod_data.get("funcs", [])
    lines = [
        f"# {main_module.title()} Module",
        "",
        f"<!-- @spec {spec_id} -->",
        "",
        "## Overview",
        "",
        f"The {main_module} module handles core functionality for the system.",
        "",
        "## Requirements",
        "",
    ]
    for i, func in enumerate(funcs[:10], 1):
        lines.append(f"- **{spec_id.split('.')[0]}.{i}**: `{func}` should work correctly")
    if len(funcs) > 10:
        lines.append(f"- ... and {len(funcs) - 10} more functions")

    lines.extend(["", "## Dependencies"])
    for imp in mod_data.get("imports", [])[:5]:
        lines.append(f"- Depends on: `{imp}`")
    lines.append("")
    return "\n".join(lines)


def generate_design(main_module: str, spec_id: str, mod_data: dict) -> str:
    """design.md を生成する。"""
    funcs = mod_data.get("funcs", [])
    lines = [
        f"# {main_module.title()} Design",
        "",
        f"<!-- @design {main_module.title()} -->",
        f"<!-- @satisfies {spec_id} -->",
        "",
        "## Architecture",
        "",
        f"The {main_module} module provides the following components:",
        "",
    ]
    for func in funcs[:8]:
        lines.append(f"- `{func}()`")
    if len(funcs) > 8:
        lines.append(f"- ... and {len(funcs) - 8} more")

    langs = mod_data.get("langs", {})
    if langs:
        lines.extend(["", "## Implementation", "",
                       f"Languages: {', '.join(f'{l}({c})' for l, c in sorted(langs.items()))}"])
    lines.append("")
    return "\n".join(lines)


def generate_tasks(main_module: str, spec_id: str, mod_data: dict) -> str:
    """tasks.md を生成する。"""
    funcs = mod_data.get("funcs", [])
    major_num = spec_id.split(".")[0]
    lines = [
        f"# {main_module.title()} Tasks",
        "",
        "| Task | Description | Requirements |",
        "|------|-------------|--------------|",
    ]
    for i, func in enumerate(funcs[:10], 1):
        task_id = f"{major_num}.{i}"
        lines.append(f"| - [ ] {task_id} | Implement `{func}` | _{spec_id}_ |")
    lines.append("")
    return "\n".join(lines)


def generate_trace_mapping(modules: dict[str, dict],
                           spec_ids: dict[str, str]) -> str:
    """.trace-mapping.yaml を生成する。"""
    lines = ["mappings:"]
    for mod_name in sorted(modules.keys()):
        mid = spec_ids[mod_name]
        mod_data = modules[mod_name]
        files = mod_data.get("files", [])
        funcs = mod_data.get("funcs", [])
        lines.append(f'  - id: "{mid}"')
        lines.append(f'    description: "{mod_name.title()} module"')
        lines.append(f'    spec:')
        lines.append(f'      - ".kiro/specs/{mod_name}/requirements.md"')
        lines.append(f'    code:')
        lines.append(f'      files:')
        for f in files[:5]:
            lines.append(f'        - "{f}"')
        if len(files) > 5:
            lines.append(f'        # ... and {len(files) - 5} more files')
        lines.append(f'      symbols:')
        for func in funcs[:8]:
            lines.append(f'        - "{func}"')
        if len(funcs) > 8:
            lines.append(f'        # ... and {len(funcs) - 8} more symbols')
        lines.append(f'    tasks:')
        for i, func in enumerate(funcs[:5], 1):
            lines.append(f'      - "{mid.split(chr(46))[0]}.{i}"')
        lines.append(f'    tags: ["@impl"]')
        lines.append("")
    return "\n".join(lines)


def insert_impl_tags(project_dir: Path, modules: dict[str, dict],
                     spec_ids: dict[str, str], dry_run: bool = False) -> list[str]:
    """コードファイルに @impl タグを挿入する。"""
    changes = []
    for mod_name, mod_data in modules.items():
        spec_id = spec_ids.get(mod_name, "0.0")
        for rel_path in mod_data.get("files", []):
            fpath = project_dir / rel_path
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # 既に @impl タグがあるか
            if IMPL_TAG_RE.search(content):
                continue

            # コメントスタイルを検出
            if content.lstrip().startswith("//") or fpath.suffix in (".c", ".h", ".cpp", ".hpp", ".cs", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".kt", ".swift"):
                tag_line = f"// @impl {spec_id}"
            else:
                tag_line = f"# @impl {spec_id}"

            # ファイル先頭のdocstring/コメントブロックの後に挿入
            lines = content.split("\n")
            insert_at = 0
            for i, line in enumerate(lines):
                if i > 20:
                    break
                stripped = line.strip()
                if stripped and not stripped.startswith(("#", "//", "/*", "*", '"', "'")):
                    insert_at = i
                    break

            lines.insert(insert_at, tag_line)
            new_content = "\n".join(lines)

            if not dry_run:
                fpath.write_text(new_content)
            changes.append(f"  + {tag_line}  → {rel_path}")

    return changes


def main():
    parser = argparse.ArgumentParser(
        description="既存コードベースをスキャンしてトレーサビリティを初期化"
    )
    parser.add_argument("--project-dir", type=str, default=".",
                        help="プロジェクトルート（デフォルト: カレント）")
    parser.add_argument("--scan-dir", type=str, default=".",
                        help="スキャンするディレクトリ（デフォルト: プロジェクトルート）")
    parser.add_argument("--lang", type=str, default="",
                        help="対象言語（カンマ区切り、例: py,ts,go,cpp。未指定=全言語）")
    parser.add_argument("--dry-run", action="store_true",
                        help="ドライラン（変更なし）")
    parser.add_argument("--no-tags", action="store_true",
                        help="@impl タグの挿入をスキップ（spec生成のみ）")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    allowed_langs = set(l.strip() for l in args.lang.split(",") if l.strip()) if args.lang else set()

    print(f"🔍 Scanning {project_dir / args.scan_dir} for code...")

    modules = detect_modules(project_dir, [args.scan_dir], allowed_langs)

    if not modules:
        print("  No code modules detected.")
        sys.exit(1)

    print(f"  Detected {len(modules)} module(s):")
    for mod_name, data in sorted(modules.items()):
        langs_str = ", ".join(data["langs"].keys())
        print(f"    {mod_name}: {len(data['files'])} files ({langs_str})")

    # 要件ID割り振り
    spec_ids = assign_spec_ids(modules)
    print(f"\n  Assigned {len(spec_ids)} spec IDs")

    # .kiro/specs/ 生成
    kiro_specs = project_dir / ".kiro" / "specs"
    if not args.dry_run:
        kiro_specs.mkdir(parents=True, exist_ok=True)

    for mod_name in sorted(modules.keys()):
        spec_id = spec_ids[mod_name]
        mod_data = modules[mod_name]
        spec_dir = kiro_specs / mod_name
        if not args.dry_run:
            spec_dir.mkdir(parents=True, exist_ok=True)

        req_content = generate_requirements(mod_name, spec_id, mod_data)
        design_content = generate_design(mod_name, spec_id, mod_data)
        tasks_content = generate_tasks(mod_name, spec_id, mod_data)

        if not args.dry_run:
            (spec_dir / "requirements.md").write_text(req_content, encoding="utf-8")
            (spec_dir / "design.md").write_text(design_content, encoding="utf-8")
            (spec_dir / "tasks.md").write_text(tasks_content, encoding="utf-8")

        print(f"  📄 .kiro/specs/{mod_name}/requirements.md  ({spec_id})")
        print(f"  📄 .kiro/specs/{mod_name}/design.md")
        print(f"  📄 .kiro/specs/{mod_name}/tasks.md")

    # .trace-mapping.yaml 生成
    tm_content = generate_trace_mapping(modules, spec_ids)
    tm_path = project_dir / ".trace-mapping.yaml"
    if not args.dry_run:
        tm_path.write_text(tm_content, encoding="utf-8")
    print(f"\n  📄 .trace-mapping.yaml  ({len(modules)} mappings)")

    # @impl タグ挿入
    if not args.no_tags:
        print(f"\n  Inserting @impl tags...")
        changes = insert_impl_tags(project_dir, modules, spec_ids, args.dry_run)
        for c in changes:
            print(f"    {c}")
        print(f"  Total: {len(changes)} tag(s) {'to insert' if args.dry_run else 'inserted'}")
    else:
        print(f"\n  (--no-tags: @impl insertion skipped)")

    print(f"\n{'✅ Dry-run complete' if args.dry_run else '✅ Brownfield init complete!'}")
    if not args.dry_run:
        print(f"\nNext steps:")
        print(f"  1. Review .kiro/specs/ and .trace-mapping.yaml")
        print(f"  2. Run: python3 .agents/scripts/check_drift.py --snapshot")
        print(f"  3. Run: python3 .agents/scripts/check-trace-completeness.py")


if __name__ == "__main__":
    main()
