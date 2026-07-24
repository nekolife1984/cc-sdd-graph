#!/usr/bin/env python3
"""check-impl-completeness.py — @impl タグの抜けチェックゲート。

.trace-mapping.yaml に登録された要件IDに対応する @impl タグが、
実際のコードに存在するかどうかを検証する。

Usage:
  # デフォルト（カレントディレクトリの .trace-mapping.yaml を読む）
  python3 .agents/scripts/check-impl-completeness.py

  # 特定のプロジェクトルートを指定
  python3 .agents/scripts/check-impl-completeness.py --project-dir strands-chat/

  # 全ソースファイルの @impl タグ有無もチェック（trace-mapping の有無問わず）
  python3 .agents/scripts/check-impl-completeness.py --check-all-sources

  # .trace-mapping.yaml のパスを明示指定
  python3 .agents/scripts/check-impl-completeness.py --trace-mapping /path/to/.trace-mapping.yaml

  # JSON 出力（CI で機械的に処理したい場合）
  python3 .agents/scripts/check-impl-completeness.py --format json

Exit codes:
  0 — All @impl tags are present and correct
  1 — One or more @impl tags are missing or mismatched
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# 対応ファイル拡張子
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift", ".sh", ".yml", ".yaml"}

# @impl タグのパターン: # @impl 1.1, 1.2  |  // @impl 2.3  |  /* @impl 3.4 */
IMPL_TAG_RE = re.compile(
    r"(?:#|//|/\*|<!--)\s*@impl\s+([\d.,\s]+?)(?:\s*$|\s*(?:#|-->|\*/))",
    re.MULTILINE,
)

# スキップするディレクトリ
SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build", ".next", "coverage", ".pytest_cache", "__init__.py"}


def load_trace_mapping(path: Path) -> list[dict]:
    """.trace-mapping.yaml を読み込み、マッピングリストを返す。"""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        mappings = data.get("mappings", []) if isinstance(data, dict) else []
        return mappings if isinstance(mappings, list) else []
    except (yaml.YAMLError, OSError) as e:
        print(f"ERROR: Failed to load {path}: {e}", file=sys.stderr)
        sys.exit(1)


def extract_impl_tags_from_file(filepath: Path) -> list[str]:
    """ファイルから @impl タグの値を抽出する。"""
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    tags = []
    for match in IMPL_TAG_RE.finditer(content):
        values = match.group(1).split(",")
        for v in values:
            v = v.strip()
            if v:
                tags.append(v)
    return tags


def scan_directory_for_impl_tags(directory: Path) -> dict[str, list[str]]:
    """ディレクトリを再帰的にスキャンし、ファイルごとの @impl タグ一覧を返す。"""
    result: dict[str, list[str]] = {}
    for ext in EXTENSIONS:
        for fpath in directory.rglob(f"*{ext}"):
            if any(part in SKIP_DIRS for part in fpath.parts):
                continue
            rel = str(fpath.relative_to(directory))
            tags = extract_impl_tags_from_file(fpath)
            if tags:
                result[rel] = tags
    return result


def find_files_without_impl_tags(directory: Path) -> list[str]:
    """@impl タグが1つもないソースファイルをリストする。"""
    untagged: list[str] = []
    for ext in EXTENSIONS:
        for fpath in directory.rglob(f"*{ext}"):
            if any(part in SKIP_DIRS for part in fpath.parts):
                continue
            rel = str(fpath.relative_to(directory))
            tags = extract_impl_tags_from_file(fpath)
            if not tags:
                untagged.append(rel)
    return sorted(untagged)


def check_mapping_completeness(
    mappings: list[dict],
    file_tags: dict[str, list[str]],
    project_dir: Path,
) -> list[dict]:
    """.trace-mapping.yaml の各マッピングに対して @impl タグの存在を検証する。"""
    findings: list[dict] = []

    for mapping in mappings:
        mid = mapping.get("id", "")
        if not mid:
            continue

        code_files = mapping.get("code", {}).get("files", [])
        if not code_files:
            continue

        # この要件IDが @impl で使われているファイルを特定
        impl_file_tags: dict[str, list[str]] = {}
        for filepath_str, tags in file_tags.items():
            for tag in tags:
                parts = [p.strip() for p in tag.replace(".", " ").split()]
                target_parts = [p.strip() for p in mid.replace(".", " ").split()]
                # 完全一致または前方一致でチェック
                if tag == mid or (tag.startswith(mid + ".")):
                    impl_file_tags.setdefault(filepath_str, []).append(tag)

        for code_file_pattern in code_files:
            code_path = project_dir / code_file_pattern
            rel_path = str(code_path.relative_to(project_dir)) if code_path.exists() else code_file_pattern

            # ワイルドカードパターンの処理
            if "*" in code_file_pattern:
                matched = list(project_dir.glob(code_file_pattern))
                if not matched:
                    findings.append({
                        "type": "FILE_NOT_FOUND",
                        "mapping_id": mid,
                        "file": code_file_pattern,
                        "detail": f"File pattern '{code_file_pattern}' does not match any files",
                    })
                continue

            if not code_path.exists():
                findings.append({
                    "type": "FILE_NOT_FOUND",
                    "mapping_id": mid,
                    "file": rel_path,
                    "detail": f"File '{rel_path}' not found on disk",
                })
                continue

            # このファイルに @impl {mid} があるか
            file_impls = file_tags.get(rel_path, [])
            mid_found = any(
                tag == mid or tag.startswith(mid + ".")
                for tag in file_impls
            )

            if not mid_found:
                # 他のファイルでタグ付されてないか確認
                other_files = [
                    f for f, ids in impl_file_tags.items()
                    if f != rel_path
                ]
                if not other_files:
                    findings.append({
                        "type": "MISSING_IMPL_TAG",
                        "mapping_id": mid,
                        "file": rel_path,
                        "detail": f"@impl {mid} is expected in '{rel_path}' but not found "
                                  f"(checked tags: {file_impls if file_impls else 'none'})",
                    })
                else:
                    findings.append({
                        "type": "IMPL_TAG_IN_DIFFERENT_FILE",
                        "mapping_id": mid,
                        "file": rel_path,
                        "detail": f"@impl {mid} is expected in '{rel_path}' but found in: {', '.join(other_files)}",
                    })

    return findings


def format_text(findings: list[dict]) -> str:
    """テキスト形式で結果を出力する。"""
    if not findings:
        return "✅ All @impl tags are present and correct."

    lines = []
    for f in findings:
        icon = {"MISSING_IMPL_TAG": "❌", "IMPL_TAG_IN_DIFFERENT_FILE": "⚠️", "FILE_NOT_FOUND": "❌"}.get(f["type"], "❌")
        lines.append(f"{icon} [{f['type']}] {f['detail']}")

    missing = [f for f in findings if f["type"] == "MISSING_IMPL_TAG"]
    diff_file = [f for f in findings if f["type"] == "IMPL_TAG_IN_DIFFERENT_FILE"]
    not_found = [f for f in findings if f["type"] == "FILE_NOT_FOUND"]

    summary_parts = []
    if missing:
        summary_parts.append(f"{len(missing)} missing @impl tag(s)")
    if diff_file:
        summary_parts.append(f"{len(diff_file)} tag(s) in wrong file")
    if not_found:
        summary_parts.append(f"{len(not_found)} file(s) not found")

    lines.append(f"\n📊 Summary: {', '.join(summary_parts)}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Check @impl tag completeness against .trace-mapping.yaml",
    )
    parser.add_argument(
        "--project-dir", type=str, default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--trace-mapping", type=str,
        help="Path to .trace-mapping.yaml (default: <project-dir>/.trace-mapping.yaml)",
    )
    parser.add_argument(
        "--check-all-sources", action="store_true",
        help="Also check that all source files have at least one @impl tag",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"ERROR: Project directory '{project_dir}' does not exist", file=sys.stderr)
        sys.exit(1)

    trace_mapping_path = Path(args.trace_mapping) if args.trace_mapping else project_dir / ".trace-mapping.yaml"

    all_findings: list[dict] = []
    has_error = False

    # ── Step 1: .trace-mapping.yaml vs @impl tags ──
    mappings = load_trace_mapping(trace_mapping_path)

    if mappings:
        file_tags = scan_directory_for_impl_tags(project_dir)
        mapping_findings = check_mapping_completeness(mappings, file_tags, project_dir)
        all_findings.extend(mapping_findings)

        if mapping_findings:
            has_error = True
    else:
        if trace_mapping_path.exists():
            print(f"⚠️  {trace_mapping_path} exists but has no valid mappings", file=sys.stderr)
        else:
            print(f"ℹ️  No .trace-mapping.yaml found at {trace_mapping_path}", file=sys.stderr)

    # ── Step 2: --check-all-sources（全ソースの @impl 有無）──
    if args.check_all_sources:
        untagged = find_files_without_impl_tags(project_dir)
        # 一般的に無視してよいファイルをフィルタ
        config_patterns = {"package.json", "tsconfig.json", "webpack.config.js", "vite.config.ts",
                          ".eslintrc", ".prettierrc", "Dockerfile", "docker-compose.yml"}
        untagged_src = [
            f for f in untagged
            if not any(f.endswith(p) or f.startswith(".") for p in config_patterns)
            and not f.startswith(".agents/")
            and not f.startswith("node_modules/")
            and not f.startswith(".venv/")
        ]
        if untagged_src:
            all_findings.append({
                "type": "MISSING_IMPL_IN_SOURCE",
                "file": "",
                "mapping_id": "",
                "detail": f"{len(untagged_src)} source file(s) without any @impl tag: "
                          f"{', '.join(untagged_src[:10])}{'...' if len(untagged_src) > 10 else ''}",
            })
            if not has_error:
                has_error = True

    # ── 出力 ──
    if args.format == "json":
        output = {
            "passed": not has_error,
            "findings_count": len(all_findings),
            "findings": all_findings,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(format_text(all_findings))

    sys.exit(1 if has_error else 0)


if __name__ == "__main__":
    main()
