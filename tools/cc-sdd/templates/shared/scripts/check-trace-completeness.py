#!/usr/bin/env python3
"""
check-trace-completeness.py — トレーサビリティ完全性チェック

コード内の @impl/@module/@feature タグと .trace-mapping.yaml,
tasks.md の一貫性を検証する包括的ゲート。

Usage:
  # 全チェック実行
  python3 .agents/scripts/check-trace-completeness.py

  # 特定のチェックのみ
  python3 .agents/scripts/check-trace-completeness.py --check impl,files,symbols,module,requirements,depends

  # プロジェクトディレクトリを指定
  python3 .agents/scripts/check-trace-completeness.py --project-dir /path/to/project

  # チェック一覧
  python3 .agents/scripts/check-trace-completeness.py --list-checks

Exit code: 0 = all passed, 1 = any check failed

Checks:
  1. impl      — @impl ↔ .trace-mapping.yaml 完全性
  2. files     — code.files 実在性 + @impl タグ一致
  3. symbols   — code.symbols 実在性（関数/クラス名）
  4. module    — @module タグ網羅性
  5. requirements — _Requirements:_ → .trace-mapping.yaml トレース
  6. depends   — _Depends:_ 構文チェック
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# ── 定数 ──
TRACE_MAPPING_PATH = Path(".trace-mapping.yaml")
TASKS_MD_PATH = Path(".kiro/specs")  # 全 feature の tasks.md をスキャン

# 対応ファイル拡張子
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift"}

# タグパターン（extract_tags.py と同一）
IMPL_TAG_RE = re.compile(r'#\s*@impl\s+(.+?)(?:\s*$|#)', re.MULTILINE)
MODULE_TAG_RE = re.compile(r'#\s*@module\s+(.+?)(?:\s*$|#)', re.MULTILINE)
FEATURE_TAG_RE = re.compile(r'#\s*@feature\s+(.+?)(?:\s*$|#)', re.MULTILINE)

# シンボルパターン（関数・クラス定義）
SYMBOL_RE = re.compile(
    r'(?:def\s+|class\s+|function\s+|const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|'
    r'fn\s+|pub\s+fn\s+|public\s+(?:static\s+)?(?:function\s+)?\w+\s*\(|'
    r'async\s+function\s+|async\s+fn\s+)'
    r'(\w+)'
)

# _Requirements: パターン
REQUIREMENTS_RE = re.compile(r'_Requirements:\s*([\d.,\s]+)')

# _Depends: パターン
DEPENDS_RE = re.compile(r'_Depends:\s*([\d.,\s]+)')

# _Boundary: パターン
BOUNDARY_RE = re.compile(r'_Boundary:\s*(.+?)(?:\s*$|_)')


# ── ユーティリティ ──

def load_mapping(project_dir: Path) -> list[dict]:
    """.trace-mapping.yaml を読み込む。"""
    path = project_dir / TRACE_MAPPING_PATH
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return []
    return data.get("mappings", [])


def find_tasks_mds(project_dir: Path) -> list[Path]:
    """プロジェクト内の全 tasks.md をスキャンする。"""
    spec_dir = project_dir / TASKS_MD_PATH
    if not spec_dir.exists():
        return []
    return list(spec_dir.rglob("tasks.md"))


def find_code_files(project_dir: Path, file_globs: list[str]) -> list[Path]:
    """code.files のパターンから実ファイルを解決する。"""
    files = []
    for pattern in file_globs:
        # グロブまたは直接パス
        p = project_dir / pattern
        if p.exists():
            files.append(p.resolve())
        else:
            # グロブとして展開
            matched = list(project_dir.glob(pattern))
            files.extend(m.resolve() for m in matched)
    return files


def scan_file_for_tags(filepath: Path) -> tuple[list[str], list[str], list[str]]:
    """ファイルから @impl, @module, @feature タグを抽出。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return [], [], []

    impls = [v.strip() for v in IMPL_TAG_RE.findall(content)]
    modules = [v.strip() for v in MODULE_TAG_RE.findall(content)]
    features = [v.strip() for v in FEATURE_TAG_RE.findall(content)]
    return impls, modules, features


def scan_file_for_symbols(filepath: Path) -> set[str]:
    """ファイルから定義されているシンボル（関数名・クラス名）を抽出。"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    return set(SYMBOL_RE.findall(content))


def requires_expand(value: str) -> list[str]:
    """_Requirements: 1.1, 1.2 や _Depends: 1.1, 2.2 をパース。"""
    ids = []
    for part in re.split(r'[,，\s]+', value):
        part = part.strip()
        if part:
            ids.append(part)
    return ids


# ── 各チェック ──

def check_impl_completeness(project_dir: Path, mappings: list[dict]) -> list[str]:
    """
    Check 1: @impl ↔ .trace-mapping.yaml 完全性
    - .trace-mapping.yaml にエントリがあるのにコードに @impl タグがない
    - コードに @impl タグがあるのに .trace-mapping.yaml にエントリがない（dual check）
    """
    issues = []

    # .trace-mapping.yaml に登録されている全 @impl 要件ID
    mapped_impl_ids: dict[str, dict] = {}
    for m in mappings:
        tags = m.get("tags", [])
        if "@impl" in tags:
            mid = m.get("id", "")
            if mid:
                mapped_impl_ids[mid] = m

    # コード上の全 @impl タグ
    code_impls: dict[str, list[Path]] = {}  # impl_id → [filepaths]
    for ext in EXTENSIONS:
        for fpath in sorted(project_dir.rglob(f"*{ext}")):
            if any(part.startswith("__") or part in (".venv", "node_modules", ".git", "dist", "build") for part in fpath.parts):
                continue
            impls, _, _ = scan_file_for_tags(fpath)
            for impl_id in impls:
                for single_id in [i.strip() for i in impl_id.replace("，", ",").split(",")]:
                    if single_id:
                        code_impls.setdefault(single_id, []).append(fpath)

    # チェックA: .trace-mapping.yaml にエントリがあるのにコードに @impl タグがない
    for mid, entry in sorted(mapped_impl_ids.items()):
        if mid not in code_impls:
            # .trace-mapping.yaml の code.files に書かれていても実ファイルにタグがない場合
            cfiles = entry.get("code", {}).get("files", [])
            found_in_files = find_code_files(project_dir, cfiles)
            if found_in_files:
                tagged = False
                for f in found_in_files:
                    impls, _, _ = scan_file_for_tags(f)
                    if any(mid in i.replace("，", ",").split(",") for i in impls):
                        tagged = True
                        break
                if not tagged:
                    issues.append(
                        f"[impl] @impl {mid}: エントリは .trace-mapping.yaml にあるが、"
                        f"参照ファイル {cfiles} に対応する @impl タグが見つからない"
                    )
            else:
                issues.append(
                    f"[impl] @impl {mid}: .trace-mapping.yaml にエントリがあるが、"
                    f"コード内に @impl {mid} タグが見つからない"
                )

    # チェックB: コードに @impl タグがあるのに .trace-mapping.yaml にエントリがない
    for impl_id, files in sorted(code_impls.items()):
        if impl_id not in mapped_impl_ids:
            file_list = ", ".join(str(f.relative_to(project_dir)) for f in files[:3])
            suffix = "..." if len(files) > 3 else ""
            issues.append(
                f"[impl] @impl {impl_id}: コード ({file_list}{suffix}) にタグがあるが、"
                f".trace-mapping.yaml にエントリがない"
            )

    return issues


def check_files_existence(project_dir: Path, mappings: list[dict]) -> list[str]:
    """
    Check 2: code.files 実在性 + @impl タグ一致
    - .trace-mapping.yaml に書かれているファイルが存在するか
    - そのファイルに @impl タグが entry.id と一致するか
    """
    issues = []

    for m in mappings:
        mid = m.get("id", "")
        cfiles = m.get("code", {}).get("files", [])
        tags = m.get("tags", [])
        if not cfiles:
            continue

        for pattern in cfiles:
            resolved = list(project_dir.glob(pattern)) if "*" in pattern else [project_dir / pattern]
            if not resolved or not any(p.exists() for p in resolved):
                issues.append(
                    f"[files] id={mid}: code.files に '{pattern}' があるが、"
                    f"ファイルが存在しない"
                )
                continue

            for fpath in resolved:
                if not fpath.exists():
                    issues.append(
                        f"[files] id={mid}: code.files の '{fpath.relative_to(project_dir)}' が存在しない"
                    )
                    continue

                # @impl タグがあるべきエントリは、ファイルに @impl タグが含まれているか
                if "@impl" in tags and mid:
                    impls, _, _ = scan_file_for_tags(fpath)
                    # mid が impl タグに含まれているか（カンマ区切り対応）
                    found = False
                    for impl_str in impls:
                        ids_in_tag = [i.strip() for i in impl_str.replace("，", ",").split(",")]
                        if mid in ids_in_tag:
                            found = True
                            break
                    if not found:
                        issues.append(
                            f"[files] id={mid}: ファイル {fpath.relative_to(project_dir)} に "
                            f"@impl {mid} タグがない"
                        )

    return issues


def check_symbols_existence(project_dir: Path, mappings: list[dict]) -> list[str]:
    """
    Check 3: code.symbols 実在性
    - .trace-mapping.yaml に書かれているシンボル（関数名/クラス名）が
      参照コードファイルに実際に存在するか
    """
    issues = []

    for m in mappings:
        mid = m.get("id", "")
        symbols = m.get("code", {}).get("symbols", [])
        cfiles = m.get("code", {}).get("files", [])
        if not symbols:
            continue

        # 参照ファイルから全シンボルを収集
        actual_symbols: set[str] = set()
        for pattern in cfiles:
            resolved = find_code_files(project_dir, [pattern])
            for fpath in resolved:
                actual_symbols.update(scan_file_for_symbols(fpath))

        for sym in symbols:
            # sym は "ClassName.method_name" の可能性
            parts = sym.split(".")
            sym_name = parts[0]  # 最低限トップレベルのシンボル名は一致してほしい
            if sym_name not in actual_symbols:
                issues.append(
                    f"[symbols] id={mid}: シンボル '{sym}' が "
                    f"code.files 内に見つからない"
                )

    return issues


def check_module_tags(project_dir: Path, mappings: list[dict]) -> list[str]:
    """
    Check 4: @module タグ網羅性
    - @module タグを持つ .trace-mapping.yaml エントリに対応する @module タグがコードにあるか
    - @impl タグのあるファイルに @module タグも推奨
    """
    issues = []

    # @module エントリのチェック
    for m in mappings:
        tags = m.get("tags", [])
        mid = m.get("id", "")
        if "@module" in tags:
            cfiles = m.get("code", {}).get("files", [])
            module_name = mid.replace("module-", "")  # "module-auth" → "auth"

            found_in_code = False
            for pattern in cfiles:
                resolved = find_code_files(project_dir, [pattern])
                for fpath in resolved:
                    _, modules, _ = scan_file_for_tags(fpath)
                    if module_name in modules:
                        found_in_code = True
                        break
                if found_in_code:
                    break

            if not found_in_code:
                issues.append(
                    f"[module] @module {module_name}: .trace-mapping.yaml にエントリがあるが、"
                    f"コード内に # @module {module_name} タグが見つからない"
                )

    # @impl タグがあるのに @module タグがないファイルを警告
    for ext in EXTENSIONS:
        for fpath in sorted(project_dir.rglob(f"*{ext}")):
            if any(part.startswith("__") or part in (".venv", "node_modules", ".git", "dist", "build") for part in fpath.parts):
                continue
            impls, modules, _ = scan_file_for_tags(fpath)
            if impls and not modules:
                # @impl があるのに @module がない（推奨レベル）
                rel = fpath.relative_to(project_dir)
                impl_list = ", ".join(impls[:3])
                issues.append(
                    f"[module] {rel}: @impl ({impl_list}) があるが @module タグがない — "
                    f"推奨: # @module <module-name> を追加"
                )

    return issues


def check_requirements_trace(project_dir: Path, mappings: list[dict]) -> list[str]:
    """
    Check 5: _Requirements:_ → .trace-mapping.yaml トレース
    - tasks.md の _Requirements: X.Y で参照されている要件IDが
      .trace-mapping.yaml にエントリとして存在するか
    """
    issues = []
    task_files = find_tasks_mds(project_dir)
    if not task_files:
        return []

    mapped_ids = {m.get("id", "") for m in mappings if m.get("id")}

    for task_file in task_files:
        try:
            content = task_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for match in REQUIREMENTS_RE.finditer(content):
            req_ids = requires_expand(match.group(1))
            for req_id in req_ids:
                if req_id not in mapped_ids:
                    rel = task_file.relative_to(project_dir)
                    issues.append(
                        f"[requirements] {rel}: _Requirements: {req_id} が参照されているが、"
                        f".trace-mapping.yaml に対応するエントリがない"
                    )

    return issues


def check_depends_syntax(project_dir: Path, mappings: list[dict]) -> list[str]:
    """
    Check 6: _Depends:_ 構文チェック
    - tasks.md の _Depends: が正しいタスクID形式か
    - 参照先のタスクIDが tasks.md 内に存在するか
    """
    issues = []
    task_files = find_tasks_mds(project_dir)
    if not task_files:
        return []

    for task_file in task_files:
        try:
            content = task_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        # 全タスクIDを収集
        task_ids: set[str] = set()
        for line in content.split("\n"):
            m = re.match(r'-\s*\[\s*[ xX]\s*\]\s+([\d.]+)', line)
            if m:
                task_ids.add(m.group(1))

        for line_no, line in enumerate(content.split("\n"), 1):
            for match in DEPENDS_RE.finditer(line):
                dep_ids = requires_expand(match.group(1))
                for dep_id in dep_ids:
                    # タスクID形式チェック（X.Y または X.Y.Z）
                    if not re.match(r'^\d+(\.\d+)*$', dep_id):
                        rel = task_file.relative_to(project_dir)
                        issues.append(
                            f"[depends] {rel}:{line_no}: _Depends: {dep_id} の形式が不正"
                        )
                    elif dep_id not in task_ids:
                        rel = task_file.relative_to(project_dir)
                        issues.append(
                            f"[depends] {rel}:{line_no}: _Depends: {dep_id} がタスク一覧に見つからない"
                        )

    return issues


# ── メイン ──

AVAILABLE_CHECKS = {
    "impl": check_impl_completeness,
    "files": check_files_existence,
    "symbols": check_symbols_existence,
    "module": check_module_tags,
    "requirements": check_requirements_trace,
    "depends": check_depends_syntax,
}


def main():
    parser = argparse.ArgumentParser(description="トレーサビリティ完全性チェック")
    parser.add_argument("--project-dir", type=str, default=".",
                        help="プロジェクトルートディレクトリ（デフォルト: カレント）")
    parser.add_argument("--check", type=str, default="all",
                        help=f"実行するチェック（カンマ区切り、デフォルト: all）。"
                             f"選択肢: {', '.join(sorted(AVAILABLE_CHECKS.keys()))}")
    parser.add_argument("--list-checks", action="store_true",
                        help="利用可能なチェック一覧を表示")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細出力（通過したチェックも表示）")
    args = parser.parse_args()

    if args.list_checks:
        print("利用可能なチェック:")
        for name, func in sorted(AVAILABLE_CHECKS.items()):
            doc_line = func.__doc__ or ""
            brief = doc_line.split("\n")[0] if doc_line else ""
            print(f"  {name:15s} — {brief}")
        sys.exit(0)

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.exists():
        print(f"ERROR: プロジェクトディレクトリ '{project_dir}' が存在しません", file=sys.stderr)
        sys.exit(1)

    # チェック選択
    if args.check == "all":
        selected = list(AVAILABLE_CHECKS.keys())
    else:
        selected = [c.strip() for c in args.check.split(",") if c.strip() in AVAILABLE_CHECKS]
        if not selected:
            print(f"ERROR: 有効なチェック名を指定してください。"
                  f"選択肢: {', '.join(sorted(AVAILABLE_CHECKS.keys()))}", file=sys.stderr)
            sys.exit(1)

    # .trace-mapping.yaml の有無
    mapping_path = project_dir / TRACE_MAPPING_PATH
    has_mapping = mapping_path.exists()
    mappings = load_mapping(project_dir) if has_mapping else []

    if not has_mapping:
        print(f"ℹ️  .trace-mapping.yaml が見つかりません — "
              f"impl/files/symbols/module チェックはスキップされます")

    total_issues = 0
    any_failed = False

    for check_name in selected:
        # mapping が必要なチェックはスキップ
        if check_name in ("impl", "files", "symbols", "module") and not has_mapping:
            if args.verbose:
                print(f"  ⏭️  {check_name}: スキップ（.trace-mapping.yaml なし）")
            continue

        check_func = AVAILABLE_CHECKS[check_name]
        issues = check_func(project_dir, mappings)
        total_issues += len(issues)

        if issues:
            any_failed = True
            for issue in issues:
                print(f"  ❌ {issue}")
        elif args.verbose:
            doc_line = (check_func.__doc__ or "").split("\n")[0] if check_func.__doc__ else check_name
            print(f"  ✅ {check_name}: 問題なし")

    # サマリー
    if any_failed:
        print(f"\n❌ FAILED: {total_issues} 個の問題が見つかりました")
        sys.exit(1)
    else:
        print(f"\n✅ ALL CHECKS PASSED: 問題なし")
        sys.exit(0)


if __name__ == "__main__":
    main()
