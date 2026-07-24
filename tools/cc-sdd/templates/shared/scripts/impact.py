#!/usr/bin/env python3
"""
impact.py — CRG (code-review-graph) + .trace-mapping.yaml による影響分析。
--quick モードでは .trace-mapping.yaml なしでも @impl/@spec/@verifies タグの
grep で簡易影響分析が可能。

Usage:
  # 仕様→コード影響（spec-id 指定）
  python3 .agents/scripts/impact.py --spec-id 1.1

  # コード→仕様影響（ファイルパス指定）
  python3 .agents/scripts/impact.py --file strands-chat/ui/chat.py

  # コード→仕様影響（diff 指定）
  python3 .agents/scripts/impact.py --diff

  # 全マッピング一覧
  python3 .agents/scripts/impact.py --list

  # CRG 連携 (JSON 出力)
  python3 .agents/scripts/impact.py --spec-id 6.1 --crg

  # --quick: .trace-mapping.yaml なしで @impl/@spec/@verifies タグを grep
  python3 .agents/scripts/impact.py --quick --file src/auth/login.py
  python3 .agents/scripts/impact.py --quick --spec-id 1.1
  python3 .agents/scripts/impact.py --quick --diff
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml


TRACE_MAPPING_PATH = Path(".trace-mapping.yaml")

# タグパターン（extract_tags.py と同一）
IMPL_TAG_RE = re.compile(r'#\s*@impl\s+(.+?)(?:\s*$|#)', re.MULTILINE)
VERIFIES_TAG_RE = re.compile(r'#\s*@verifies\s+(.+?)(?:\s*$|#)', re.MULTILINE)
SPEC_TAG_RE = re.compile(r'<!--\s*@spec\s+(.+?)\s*-->', re.MULTILINE)
DESIGN_TAG_RE = re.compile(r'<!--\s*@design\s+(.+?)\s*-->', re.MULTILINE)

# テストファイルパターン（check-trace-completeness.py と同一）
TEST_FILE_PATTERNS = [
    "**/test_*.py", "**/*_test.py",
    "**/*.test.ts", "**/*.test.tsx",
    "**/*.spec.ts", "**/*.spec.tsx",
    "**/*_test.go",
    "**/*_test.rs",
    "**/*Test*.java",
    "**/*Test*.kt",
    "**/*Test*.swift",
    "**/*Test*.rb", "**/*_test.rb",
]

# 除外ディレクトリ
EXCLUDE_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build", ".artgraph", ".trace"}


def load_mapping(path: Path = TRACE_MAPPING_PATH) -> list[dict]:
    """.trace-mapping.yaml を読み込む。"""
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return []
    return data.get("mappings", [])


def find_by_spec_id(mappings: list[dict], spec_id: str) -> list[dict]:
    """spec-id に一致するマッピングを検索する。"""
    results = []
    for m in mappings:
        if m.get("id") == spec_id:
            results.append(m)
    return results


def find_by_file(mappings: list[dict], filepath: str) -> list[dict]:
    """ファイルパスに一致するマッピングを検索する。"""
    results = []
    target = Path(filepath).resolve()
    for m in mappings:
        for code_file in m.get("code", {}).get("files", []):
            if Path(code_file).resolve() == target:
                results.append(m)
                break
    return results


def find_by_symbol(mappings: list[dict], symbol: str) -> list[dict]:
    """シンボル名に一致するマッピングを検索する。"""
    results = []
    for m in mappings:
        if symbol in m.get("code", {}).get("symbols", []):
            results.append(m)
    return results


# ── CRG 連携 ──


def run_crg_query(tool: str, params: dict) -> Optional[dict]:
    """CRG クエリを外部ツール/コマンド経由で実行する（利用可能な場合）。"""
    hook = os.environ.get("CRG_HOOK", "")
    if hook:
        try:
            input_data = json.dumps({"tool": tool, "params": params})
            result = subprocess.run(
                [hook],
                input=input_data,
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            print(f"[CRG] Hook error: {e}", file=sys.stderr)

    if shutil.which("crg-query"):
        try:
            input_data = json.dumps({"tool": tool, "params": params})
            result = subprocess.run(
                ["crg-query"],
                input=input_data,
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
            pass

    crg_cli = shutil.which("code-review-graph")
    if crg_cli:
        query_map = {
            "query_graph_tool": {
                "callers_of": "callers_of", "callees_of": "callees_of",
                "imports_of": "imports_of", "tests_for": "tests_for",
            },
        }
        if tool == "query_graph_tool":
            pattern = params.get("pattern", "")
            if pattern in query_map["query_graph_tool"]:
                target = params.get("target", params.get("symbol", ""))
                if target:
                    subcmd = query_map["query_graph_tool"][pattern]
                    return _run_crg_cli_query(subcmd, target, crg_cli)
        if tool == "get_impact_radius_tool":
            symbol = params.get("symbol", "")
            if symbol:
                result = {"symbol": symbol, "callers": [], "callees": [], "importers": []}
                cr = _run_crg_cli_query("callers_of", symbol, crg_cli)
                if cr: result["callers"] = cr
                cr = _run_crg_cli_query("callees_of", symbol, crg_cli)
                if cr: result["callees"] = cr
                cr = _run_crg_cli_query("importers_of", symbol, crg_cli)
                if cr: result["importers"] = cr
                return result
        if tool == "get_affected_flows_tool":
            target = params.get("target", params.get("symbol", ""))
            if target:
                result = {"target": target, "callers": [], "callees": []}
                cr = _run_crg_cli_query("callers_of", target, crg_cli)
                if cr: result["callers"] = cr
                cr = _run_crg_cli_query("callees_of", target, crg_cli)
                if cr: result["callees"] = cr
                return result
        if tool == "semantic_search_nodes_tool":
            query = params.get("query", params.get("symbol", ""))
            if query:
                result = _run_crg_cli_query("file_summary", query, crg_cli)
                if result is not None:
                    return {"results": result if isinstance(result, list) else [result]}

    print("[CRG] No CRG tool available (pip install code-review-graph && code-review-graph build)",
          file=sys.stderr)
    return None


def _run_crg_cli_query(subcommand: str, target: str, cli_path: str) -> Optional[Any]:
    """Run a single code-review-graph query subcommand."""
    try:
        result = subprocess.run(
            [cli_path, "query", subcommand, target, "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


# ── 標準モード（.trace-mapping.yaml 必要） ──


def impact_from_spec(mappings: list[dict], spec_id: str, use_crg: bool = False) -> dict:
    """仕様 ID から影響範囲を分析する。"""
    matched = find_by_spec_id(mappings, spec_id)
    if not matched:
        return {"error": f"spec-id '{spec_id}' not found in .trace-mapping.yaml"}

    result: dict[str, Any] = {
        "query_type": "spec\u2192code",
        "spec_id": spec_id,
        "files": [],
        "symbols": [],
        "tasks": [],
        "docs": [],
        "affected_mappings": [],
    }

    for m in matched:
        result["files"].extend(m.get("code", {}).get("files", []))
        result["symbols"].extend(m.get("code", {}).get("symbols", []))
        result["tasks"].extend(m.get("tasks", []))
        result["docs"].extend(m.get("docs", []))
        result["affected_mappings"].append(m["id"])

    result["files"] = sorted(set(result["files"]))
    result["symbols"] = sorted(set(result["symbols"]))
    result["tasks"] = sorted(set(result["tasks"]))
    result["docs"] = sorted(set(result["docs"]))

    if use_crg:
        for symbol in result["symbols"]:
            crg_result = run_crg_query("get_impact_radius_tool", {"symbol": symbol})
            result.setdefault("crg_impact", []).append({
                "symbol": symbol,
                "crg_result": crg_result,
            })

    return result


def impact_from_code(mappings: list[dict], filepath: str, use_crg: bool = False) -> dict:
    """コードファイルの変更から影響を受ける spec を分析する。"""
    matched = find_by_file(mappings, filepath)
    if not matched:
        matched = find_by_symbol(mappings, Path(filepath).stem)

    if not matched:
        return {"error": f"'{filepath}' not found in .trace-mapping.yaml"}

    result: dict[str, Any] = {
        "query_type": "code\u2192spec",
        "file": filepath,
        "affected_specs": [],
        "affected_requirements": [],
        "affected_tasks": [],
        "affected_design_sections": [],
    }

    for m in matched:
        result["affected_specs"].append(m["spec"])
        result["affected_requirements"].append(m["id"])
        result["affected_tasks"].extend(m.get("tasks", []))
        if m.get("design"):
            result["affected_design_sections"].append(m["design"])

    result["affected_requirements"] = sorted(set(result["affected_requirements"]))
    result["affected_tasks"] = sorted(set(result["affected_tasks"]))
    result["affected_design_sections"] = sorted(set(result["affected_design_sections"]))

    if use_crg:
        for req in result["affected_requirements"]:
            crg_result = run_crg_query("get_affected_flows_tool", {"target": filepath})
            result.setdefault("crg_flows", []).append({
                "requirement": req,
                "crg_result": crg_result,
            })

    return result


def impact_from_diff(mappings: list[dict], use_crg: bool = False) -> dict:
    """git diff から変更ファイルを取得し、影響分析する。"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, check=True,
        )
        changed_files = [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("WARNING: git diff failed", file=sys.stderr)
        return {"error": "git diff failed", "note": "not a git repo or no changes"}

    if not changed_files:
        return {"note": "no uncommitted changes"}

    all_results = []
    for f in changed_files:
        r = impact_from_code(mappings, f, use_crg)
        if "error" not in r:
            all_results.append(r)

    return {
        "query_type": "diff\u2192spec",
        "changed_files": changed_files,
        "results": all_results,
    }


# ── Quick モード（.trace-mapping.yaml 不要） ──


def _grep_tags(project_dir: Path, tag_re: re.Pattern, file_suffixes: tuple[str, ...]) -> dict[str, list[str]]:
    """プロジェクト内のファイルからタグを grep して {tag_value: [filepath]} を返す。"""
    results: dict[str, set[str]] = {}
    for suffix in file_suffixes:
        for fpath in project_dir.rglob(f"*{suffix}"):
            if any(part in EXCLUDE_DIRS for part in fpath.parts):
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for match in tag_re.finditer(content):
                values = [v.strip() for v in match.group(1).replace("\uff0c", ",").split(",") if v.strip()]
                for val in values:
                    results.setdefault(val, set()).add(str(fpath))
    return {k: sorted(v) for k, v in results.items()}


def _grep_impl_tags(project_dir: Path) -> dict[str, list[str]]:
    """@impl タグを grep。"""
    code_suffixes = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift")
    return _grep_tags(project_dir, IMPL_TAG_RE, code_suffixes)


def _grep_verifies_tags(project_dir: Path) -> dict[str, list[str]]:
    """@verifies タグを grep（テストファイルのみ）。"""
    test_suffixes = tuple(
        set(p.split("*")[-1] for p in TEST_FILE_PATTERNS if p.endswith(".*"))
    )
    return _grep_tags(project_dir, VERIFIES_TAG_RE, test_suffixes)


def _grep_spec_tags(project_dir: Path) -> dict[str, list[str]]:
    """@spec タグを grep（.md ファイルのみ）。"""
    return _grep_tags(project_dir, SPEC_TAG_RE, (".md",))


def _grep_design_tags(project_dir: Path) -> dict[str, list[str]]:
    """@design タグを grep（.md ファイルのみ）。"""
    return _grep_tags(project_dir, DESIGN_TAG_RE, (".md",))


def quick_impact_from_file(project_dir: Path, filepath: str) -> dict:
    """
    --quick --file <path>: .trace-mapping.yaml なしでファイルの @impl タグから
    関連する spec やテストを grep で見つける。
    """
    target = Path(filepath)
    if not target.exists():
        # 相対パスとして解決
        target = project_dir / filepath
    if not target.exists():
        return {"error": f"file not found: {filepath}"}

    rel = str(target.relative_to(project_dir)) if target.is_relative_to(project_dir) else filepath

    # 対象ファイルの @impl タグを読む
    impl_ids: list[str] = []
    try:
        content = target.read_text(encoding="utf-8")
        for match in IMPL_TAG_RE.finditer(content):
            ids = [v.strip() for v in match.group(1).replace("\uff0c", ",").split(",") if v.strip()]
            impl_ids.extend(ids)
    except (UnicodeDecodeError, OSError):
        pass

    if not impl_ids:
        return {
            "note": f"no @impl tags found in {rel}",
            "file": rel,
            "query_type": "quick-file",
        }

    # 全 @impl / @verifies / @spec を grep
    impls = _grep_impl_tags(project_dir)
    vers = _grep_verifies_tags(project_dir)
    specs = _grep_spec_tags(project_dir)

    related: dict[str, Any] = {
        "file": rel,
        "query_type": "quick-file",
        "impl_tags": impl_ids,
        "related_impl_files": {},
        "related_tests": {},
        "related_specs": {},
    }

    for rid in impl_ids:
        # 同じ @impl を持つ他のファイル
        related["related_impl_files"][rid] = [
            f for f in impls.get(rid, []) if f != str(target)
        ]
        # @verifies があるテスト
        related["related_tests"][rid] = vers.get(rid, [])
        # @spec がある requirements
        related["related_specs"][rid] = specs.get(rid, [])

    return related


def quick_impact_from_spec(project_dir: Path, spec_id: str) -> dict:
    """
    --quick --spec-id <id>: .trace-mapping.yaml なしで要件IDから
    関連する実装コードやテストを grep で見つける。
    """
    impls = _grep_impl_tags(project_dir)
    vers = _grep_verifies_tags(project_dir)
    specs = _grep_spec_tags(project_dir)
    designs = _grep_design_tags(project_dir)

    result: dict[str, Any] = {
        "spec_id": spec_id,
        "query_type": "quick-spec",
        "impl_files": impls.get(spec_id, []),
        "test_files": vers.get(spec_id, []),
        "spec_files": specs.get(spec_id, []),
        "design_files": designs.get(spec_id, []),
    }

    # 合体（.trace-mapping.yaml ライクに整形）
    if result["impl_files"] or result["test_files"] or result["spec_files"]:
        result["mapping"] = {
            "id": spec_id,
            "spec": result["spec_files"],
            "code": {"files": result["impl_files"]},
            "tests": result["test_files"],
            "design": result["design_files"],
        }
    else:
        result["note"] = f"no tags found for spec-id '{spec_id}' anywhere in project"

    return result


def quick_impact_from_diff(project_dir: Path) -> dict:
    """
    --quick --diff: git diff から quick モードで影響分析。
    """
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, check=True,
            cwd=project_dir,
        )
        changed_files = [f for f in proc.stdout.strip().split("\n") if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"error": "git diff failed", "note": "not a git repo or no changes"}

    if not changed_files:
        return {"note": "no uncommitted changes"}

    all_results = []
    for f in changed_files:
        r = quick_impact_from_file(project_dir, f)
        if "error" not in r:
            all_results.append(r)

    return {
        "query_type": "quick-diff",
        "changed_files": changed_files,
        "results": all_results,
    }


# ── メイン ──


def _print_human(result: dict):
    """人間可読な形式で出力する。"""
    if "error" in result:
        print(f"\u274c {result['error']}")
        if "note" in result:
            print(f"   {result['note']}")
        return

    if "note" in result and not result.get("impl_tags"):
        print(f"\u2139\ufe0f  {result['note']}")
        return

    if "mapping_count" in result:
        print(f"\U0001f4cb Total mappings: {result['mapping_count']}")
        for m in result["mappings"]:
            desc = m.get("description") or "(no description)"
            print(f"  [{m['id']}] {desc}")
            for f in m.get("code", {}).get("files", []):
                print(f"    \u2192 {f}")
        return

    qtype = result.get("query_type", "")

    # Quick モード出力
    if qtype == "quick-file":
        print(f"\U0001f50d Quick Impact: {result['file']}")
        print(f"  @impl tags: {', '.join(result['impl_tags'])}")
        for rid in result["impl_tags"]:
            impls = result["related_impl_files"].get(rid, [])
            tests = result["related_tests"].get(rid, [])
            specs = result["related_specs"].get(rid, [])
            if impls:
                print(f"  [{rid}] \U0001f4c4 Related code ({len(impls)}):")
                for f in impls[:5]:
                    print(f"         {f}")
                if len(impls) > 5:
                    print(f"         ... and {len(impls)-5} more")
            if tests:
                print(f"  [{rid}] \U0001f9ea Tests ({len(tests)}):")
                for f in tests[:3]:
                    print(f"         {f}")
                if len(tests) > 3:
                    print(f"         ... and {len(tests)-3} more")
            if specs:
                print(f"  [{rid}] \U0001f4dd Spec:")
                for f in specs:
                    print(f"         {f}")
        return

    if qtype == "quick-spec":
        print(f"\U0001f50d Quick Impact: spec-id {result['spec_id']}")
        impls = result.get("impl_files", [])
        tests = result.get("test_files", [])
        specs = result.get("spec_files", [])
        designs = result.get("design_files", [])
        if impls:
            print(f"  \U0001f4c4 Code ({len(impls)}):")
            for f in impls[:5]:
                print(f"    {f}")
            if len(impls) > 5:
                print(f"    ... and {len(impls)-5} more")
        if tests:
            print(f"  \U0001f9ea Tests ({len(tests)}):")
            for f in tests[:5]:
                print(f"    {f}")
            if len(tests) > 5:
                print(f"    ... and {len(tests)-5} more")
        if specs:
            print(f"  \U0001f4dd Spec files ({len(specs)}):")
            for f in specs:
                print(f"    {f}")
        if designs:
            print(f"  \U0001f3e0 Design references ({len(designs)}):")
            for f in designs:
                print(f"    {f}")
        if not impls and not tests:
            print(f"  \u2139\ufe0f  {result.get('note', 'no related artifacts found')}")
        return

    if qtype == "quick-diff":
        print(f"\U0001f50d Quick Impact: git diff")
        print(f"  Changed files ({len(result['changed_files'])}):")
        for f in result["changed_files"]:
            print(f"    \U0001f4c4 {f}")
        for r in result.get("results", []):
            if r.get("impl_tags"):
                print(f"  \u2192 {r['file']}:")
                print(f"     @impl tags: {', '.join(r['impl_tags'])}")
        return

    # 標準モード出力
    if qtype == "spec\u2192code":
        print(f"\U0001f50d Spec {result['spec_id']} \u2192 Code Impact")
        print(f"  Files ({len(result['files'])}):")
        for f in result["files"]:
            print(f"    \U0001f4c4 {f}")
        print(f"  Symbols ({len(result['symbols'])}):")
        for s in result["symbols"]:
            print(f"    \U0001f527 {s}")
        print(f"  Tasks ({len(result['tasks'])}):")
        for t in result["tasks"]:
            print(f"    \U0001f4cb {t}")
        print(f"  Docs ({len(result['docs'])}):")
        for d in result["docs"]:
            print(f"    \U0001f4dd {d}")
        if "crg_impact" in result:
            print("  CRG Impact:")
            for ci in result["crg_impact"]:
                print(f"    {ci['symbol']}: {ci['crg_result']}")

    elif qtype == "code\u2192spec":
        print(f"\U0001f50d {result['file']} \u2192 Spec Impact")
        print(f"  Requirements ({len(result['affected_requirements'])}):")
        for r in result["affected_requirements"]:
            print(f"    \U0001f4cb {r}")
        print(f"  Tasks ({len(result['affected_tasks'])}):")
        for t in result["affected_tasks"]:
            print(f"    \U0001f4cb {t}")
        print(f"  Design sections ({len(result['affected_design_sections'])}):")
        for d in result["affected_design_sections"]:
            print(f"    \U0001f4dd {d}")
        print(f"  Spec files:")
        for s in result["affected_specs"]:
            print(f"    \U0001f4c4 {s}")

    elif qtype == "diff\u2192spec":
        print(f"\U0001f50d git diff \u2192 Spec Impact")
        print(f"  Changed files ({len(result['changed_files'])}):")
        for f in result["changed_files"]:
            print(f"    \U0001f4c4 {f}")
        for r in result.get("results", []):
            file_label = r.get("file", "unknown")
            reqs = ", ".join(r.get("affected_requirements", []))
            tasks = ", ".join(r.get("affected_tasks", []))
            if reqs:
                print(f"    {file_label}: Requirements: {reqs}")
            if tasks:
                print(f"    {file_label}: Tasks: {tasks}")


def main():
    parser = argparse.ArgumentParser(description="CRG + .trace-mapping.yaml 影響分析、または --quick 簡易影響分析")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--spec-id", type=str, help="影響分析: 仕様IDからコード影響")
    group.add_argument("--file", type=str, help="影響分析: コードファイルから仕様影響")
    group.add_argument("--diff", action="store_true", help="影響分析: git diff から")
    group.add_argument("--list", action="store_true", help="全マッピング一覧")
    parser.add_argument("--crg", action="store_true", help="CRG (code-review-graph) ツールと連携")
    parser.add_argument("--crg-hook", type=str, help="CRG クエリ用の外部スクリプト")
    parser.add_argument("--json", action="store_true", help="JSON 出力")
    parser.add_argument("--quick", action="store_true", help=".trace-mapping.yaml 不要の簡易モード（@impl/@spec/@verifies を grep）")
    parser.add_argument("--project-dir", type=str, default=".",
                        help="プロジェクトルート（--quick モード用、デフォルト: カレント）")
    args = parser.parse_args()

    if args.crg_hook:
        os.environ["CRG_HOOK"] = args.crg_hook

    project_dir = Path(args.project_dir).resolve()

    result: dict[str, Any] = {}

    if args.quick:
        # Quick モード: .trace-mapping.yaml 不要
        if args.spec_id:
            result = quick_impact_from_spec(project_dir, args.spec_id)
        elif args.file:
            result = quick_impact_from_file(project_dir, args.file)
        elif args.diff:
            result = quick_impact_from_diff(project_dir)
        elif args.list:
            result = {"note": "--list is not supported in --quick mode"}
    else:
        # 標準モード: .trace-mapping.yaml 必須
        mappings = load_mapping(project_dir / TRACE_MAPPING_PATH)
        if not mappings:
            print(f"ERROR: {TRACE_MAPPING_PATH} not found or empty. Use --quick for grep-based analysis.",
                  file=sys.stderr)
            sys.exit(1)

        if args.list:
            result = {"mapping_count": len(mappings), "mappings": mappings}
        elif args.spec_id:
            result = impact_from_spec(mappings, args.spec_id, args.crg)
        elif args.file:
            result = impact_from_code(mappings, args.file, args.crg)
        elif args.diff:
            result = impact_from_diff(mappings, args.crg)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
