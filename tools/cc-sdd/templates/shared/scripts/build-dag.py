#!/usr/bin/env python3
"""
build-dag.py — 軽量import依存グラフを構築する（CRG代替）

プロジェクト内の全ソースファイルから import/require/include 文を抽出し、
依存関係のDAG（有向非巡回グラフ）を JSON ファイルとして出力する。

CRG (code-review-graph) がなくても推移的影響分析を可能にする。

Usage:
  # DAGを構築
  python3 .agents/scripts/build-dag.py

  # 出力ファイルを指定
  python3 .agents/scripts/build-dag.py --output .kiro/graph/dag.json

  # プロジェクトディレクトリ指定
  python3 .agents/scripts/build-dag.py --project-dir /path/to/project

  # verbose
  python3 .agents/scripts/build-dag.py --verbose

Output:
  .kiro/graph/dag.json  — デフォルト出力先
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional


# ── 対応言語のimportパターン ──
# 各拡張子に対して、(import文を抽出する正規表現, importeeを正規化する関数)
# のタプルを定義。capture group 1 が importee 文字列。

IMPORT_PATTERNS: dict[str, list[tuple[re.Pattern, callable]]] = {
    ".py": [
        (re.compile(r'^from\s+([\w.]+)\s+import', re.MULTILINE),
         lambda s: s.replace(".", "/") + ".py"),
        (re.compile(r'^import\s+([\w.\s,]+)', re.MULTILINE),
         lambda s: [x.strip().replace(".", "/") + ".py" for x in s.split(",") if x.strip()]),
    ],
    ".ts": [
        (re.compile(r"""import\s+(?:\w+\s+from\s+)?['"](.+?)['"]"""),
         lambda s: s),
    ],
    ".tsx": [
        (re.compile(r"""import\s+(?:\w+\s+from\s+)?['"](.+?)['"]"""),
         lambda s: s),
    ],
    ".js": [
        (re.compile(r"""import\s+(?:\w+\s+from\s+)?['"](.+?)['"]"""),
         lambda s: s),
        (re.compile(r"""require\(['"](.+?)['"]\)"""),
         lambda s: s),
    ],
    ".jsx": [
        (re.compile(r"""import\s+(?:\w+\s+from\s+)?['"](.+?)['"]"""),
         lambda s: s),
        (re.compile(r"""require\(['"](.+?)['"]\)"""),
         lambda s: s),
    ],
    ".go": [
        (re.compile(r'^import\s+["](.+?)["]', re.MULTILINE),
         lambda s: s),
        (re.compile(r'^import\s+\(([^)]+)\)', re.MULTILINE | re.DOTALL),
         lambda s: [line.strip().strip('"') for line in s.split("\n")
                    if line.strip() and not line.strip().startswith("//")]),
    ],
    ".rs": [
        (re.compile(r'^use\s+([\w:]+)', re.MULTILINE),
         lambda s: s.replace("::", "/") + ".rs"),
    ],
    ".rb": [
        (re.compile(r"^require\s+['\"](.+?)['\"]", re.MULTILINE),
         lambda s: s),
        (re.compile(r"^require_relative\s+['\"](.+?)['\"]", re.MULTILINE),
         lambda s: s),
    ],
    ".java": [
        (re.compile(r'^import\s+([\w.*]+);', re.MULTILINE),
         lambda s: s.replace(".", "/").replace("*", "") + ".java"),
    ],
    ".kt": [
        (re.compile(r'^import\s+([\w.*]+)', re.MULTILINE),
         lambda s: s.replace(".", "/").replace("*", "") + ".kt"),
    ],
    ".swift": [
        (re.compile(r'^import\s+(?:class\s+)?(?:func\s+)?(\w+)', re.MULTILINE),
         lambda s: s.lower() + ".swift"),
    ],
    # ── C/C++/C# ──
    ".c": [
        (re.compile(r'#include\s+[<"](.+?)[>"]'),
         lambda s: s),
    ],
    ".h": [
        (re.compile(r'#include\s+[<"](.+?)[>"]'),
         lambda s: s),
    ],
    ".cpp": [
        (re.compile(r'#include\s+[<"](.+?)[>"]'),
         lambda s: s),
    ],
    ".hpp": [
        (re.compile(r'#include\s+[<"](.+?)[>"]'),
         lambda s: s),
    ],
    ".cs": [
        (re.compile(r'^using\s+(?:static\s+)?([\w.]+);', re.MULTILINE),
         lambda s: s.replace(".", "/") + ".cs"),
    ],
}

# ── @impl タグパターン（# と // の両方に対応） ──
IMPL_TAG_RE = re.compile(r'(?:#|//)\s*@impl\s+([\d.]+(?:,\s*[\d.]+)*)', re.MULTILINE)

# 除外ディレクトリ
EXCLUDE_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build",
                ".artgraph", ".trace", ".kiro", "bin", "obj", ".vs", "packages"}

# サポートする拡張子（全言語）
SUPPORTED_EXTENSIONS = set(IMPORT_PATTERNS.keys())


def resolve_import_path(importee: str, source_file: Path, project_dir: Path) -> Optional[str]:
    """importee 文字列から実際のファイルパスを解決する。"""
    # 相対パスの解決（./ や ../）
    if importee.startswith("./") or importee.startswith("../"):
        resolved = (source_file.parent / importee).resolve()
        # 拡張子なしの場合は試す
        if not resolved.suffix:
            for ext in SUPPORTED_EXTENSIONS:
                candidate = resolved.with_suffix(ext)
                if candidate.exists():
                    return str(candidate.relative_to(project_dir))
            # ディレクトリ/index パターン
            for ext in SUPPORTED_EXTENSIONS:
                candidate = resolved / f"index{ext}"
                if candidate.exists():
                    return str(candidate.relative_to(project_dir))
        elif resolved.exists():
            return str(resolved.relative_to(project_dir))
        return None

    # 絶対パスライク（プロジェクトルートからの相対）
    # 拡張子なし補完
    if not Path(importee).suffix:
        candidates = []
        for ext in SUPPORTED_EXTENSIONS:
            p = project_dir / f"{importee}{ext}"
            if p.exists():
                candidates.append(str(p.relative_to(project_dir)))
            # ディレクトリ/index パターン
            p = project_dir / importee / f"index{ext}"
            if p.exists():
                candidates.append(str(p.relative_to(project_dir)))
        return candidates[0] if candidates else None

    p = project_dir / importee
    if p.exists():
        return str(p.relative_to(project_dir))
    return None


def scan_file_imports(filepath: Path, project_dir: Path) -> list[str]:
    """1ファイルのimportを抽出し、解決済みの相対パス一覧を返す。"""
    ext = filepath.suffix.lower()
    if ext not in IMPORT_PATTERNS:
        return []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    resolved_imports = []
    for pattern, normalizer in IMPORT_PATTERNS[ext]:
        for match in pattern.finditer(content):
            raw = match.group(1)
            try:
                importees = normalizer(raw)
            except Exception:
                continue
            if isinstance(importees, str):
                importees = [importees]
            for imp in importees:
                imp = imp.strip()
                if not imp:
                    continue
                resolved = resolve_import_path(imp, filepath, project_dir)
                if resolved and resolved != str(filepath.relative_to(project_dir)):
                    resolved_imports.append(resolved)

    return sorted(set(resolved_imports))


def scan_impl_tags(filepath: Path) -> list[str]:
    """ファイルから @impl タグを抽出。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    tags = []
    for match in IMPL_TAG_RE.finditer(content):
        ids = [v.strip() for v in match.group(1).replace("，", ",").split(",") if v.strip()]
        tags.extend(ids)
    return sorted(set(tags))


def main():
    parser = argparse.ArgumentParser(
        description="軽量import依存グラフ（DAG）を構築する"
    )
    parser.add_argument("--project-dir", type=str, default=".",
                        help="プロジェクトルート（デフォルト: カレント）")
    parser.add_argument("--output", type=str, default=".kiro/graph/dag.json",
                        help="出力JSONパス（デフォルト: .kiro/graph/dag.json）")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細出力")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = project_dir / output_path

    if not project_dir.exists():
        print(f"ERROR: プロジェクトディレクトリ '{project_dir}' が存在しません",
              file=sys.stderr)
        sys.exit(1)

    print(f"🔍 Scanning {project_dir} for imports...")

    # 全ファイルをスキャン
    file_data: dict[str, dict] = {}
    total_files = 0

    for ext in SUPPORTED_EXTENSIONS:
        for fpath in sorted(project_dir.rglob(f"*{ext}")):
            if any(part in EXCLUDE_DIRS for part in fpath.parts):
                continue
            rel = str(fpath.relative_to(project_dir))
            imports = scan_file_imports(fpath, project_dir)
            impl_tags = scan_impl_tags(fpath)

            if imports or impl_tags or args.verbose:
                file_data[rel] = {
                    "imports": imports,
                    "imported_by": [],  # 後で計算
                    "impl_tags": impl_tags,
                }
                total_files += 1

    # imported_by を計算（逆引き）
    for rel, data in file_data.items():
        for imp in data["imports"]:
            if imp in file_data:
                file_data[imp].setdefault("imported_by", []).append(rel)

    # spec_impact マップを構築
    spec_impact: dict[str, dict] = {}
    for rel, data in file_data.items():
        for tag in data["impl_tags"]:
            if tag not in spec_impact:
                spec_impact[tag] = {"direct": [], "transitive": [], "hops": {}}
            if rel not in spec_impact[tag]["direct"]:
                spec_impact[tag]["direct"].append(rel)
            spec_impact[tag]["hops"][rel] = 0

    # 推移的影響をBFSで計算
    for spec_id, impact in spec_impact.items():
        visited = set(impact["direct"])
        queue = list(impact["direct"])
        while queue:
            current = queue.pop(0)
            if current not in file_data:
                continue
            for imp in file_data[current].get("imports", []):
                if imp not in visited and imp in file_data:
                    visited.add(imp)
                    queue.append(imp)
                    if imp not in impact["direct"] and imp not in impact["transitive"]:
                        impact["transitive"].append(imp)
                    # hops を計算
                    if imp not in impact["hops"]:
                        for d in impact["direct"]:
                            if d in file_data and imp in file_data[d].get("imports", []):
                                impact["hops"][imp] = 1
                                break
                        else:
                            impact["hops"][imp] = 2  # 2+ hops

    # DAG を構築
    dag = {
        "version": 2,
        "generated": __import__("datetime").datetime.now().isoformat(),
        "project": str(project_dir),
        "file_count": total_files,
        "files": file_data,
        "spec_impact": spec_impact,
    }

    # 出力
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dag, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n✅ DAG saved: {output_path}")
    print(f"   Files scanned: {total_files}")
    print(f"   Spec IDs found: {len(spec_impact)}")
    if args.verbose:
        for spec_id, imp in sorted(spec_impact.items()):
            print(f"     [{spec_id}] direct={len(imp['direct'])}, "
                  f"transitive={len(imp['transitive'])}")


if __name__ == "__main__":
    main()
