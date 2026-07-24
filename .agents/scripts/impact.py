#!/usr/bin/env python3
"""impact.py — CRG (code-review-graph) + .trace-mapping.yaml による影響分析。

仕様変更→コード影響、コード変更→仕様影響の双方向トレースを行う。

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
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml


TRACE_MAPPING_PATH = Path(".trace-mapping.yaml")


def load_mapping(path: Path = TRACE_MAPPING_PATH) -> list[dict]:
    """.trace-mapping.yaml を読み込む。"""
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        data = yaml.safe_load(f)
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


def run_crg_query(tool: str, params: dict) -> Optional[dict]:
    """CRG クエリを外部ツール/コマンド経由で実行する（利用可能な場合）。

    環境変数 CRG_HOOK または --crg-hook で指定された外部スクリプトがあれば、
    それを呼び出す。無い場合はスタブとして動作する。
    """
    import os
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
            print(f"[CRG] Hook returned exit {result.returncode}: {result.stderr}", file=sys.stderr)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            print(f"[CRG] Hook error: {e}", file=sys.stderr)
        return None

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

    # Fallback: code-review-graph query CLI (installed via setup-crg.sh)
    # Map CRG MCP tool names to code-review-graph query subcommands
    crg_cli = shutil.which("code-review-graph")
    if crg_cli:
        query_map = {
            "query_graph_tool": {
                "callers_of": "callers_of", "callees_of": "callees_of",
                "imports_of": "imports_of", "tests_for": "tests_for",
            },
        }
        # Try direct query_graph_tool mapping
        if tool == "query_graph_tool":
            pattern = params.get("pattern", "")
            if pattern in query_map["query_graph_tool"]:
                target = params.get("target", params.get("symbol", ""))
                if target:
                    subcmd = query_map["query_graph_tool"][pattern]
                    return _run_crg_cli_query(subcmd, target, crg_cli)

        # get_impact_radius_tool: collect callers + callees + importers
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

        # get_affected_flows_tool: callers + callees
        if tool == "get_affected_flows_tool":
            target = params.get("target", params.get("symbol", ""))
            if target:
                result = {"target": target, "callers": [], "callees": []}
                cr = _run_crg_cli_query("callers_of", target, crg_cli)
                if cr: result["callers"] = cr
                cr = _run_crg_cli_query("callees_of", target, crg_cli)
                if cr: result["callees"] = cr
                return result

        # semantic_search_nodes_tool: file_summary
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


def impact_from_spec(mappings: list[dict], spec_id: str, use_crg: bool = False) -> dict:
    """仕様 ID から影響範囲を分析する。"""
    matched = find_by_spec_id(mappings, spec_id)
    if not matched:
        return {"error": f"spec-id '{spec_id}' not found in .trace-mapping.yaml"}

    result: dict[str, Any] = {
        "query_type": "spec→code",
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

    # 重複除去・ソート
    result["files"] = sorted(set(result["files"]))
    result["symbols"] = sorted(set(result["symbols"]))
    result["tasks"] = sorted(set(result["tasks"]))
    result["docs"] = sorted(set(result["docs"]))

    if use_crg:
        # CRG で各シンボルの impact radius を取得
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
        # シンボルレベルでも検索
        matched = find_by_symbol(mappings, Path(filepath).stem)

    if not matched:
        return {"error": f"'{filepath}' not found in .trace-mapping.yaml"}

    result: dict[str, Any] = {
        "query_type": "code→spec",
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
        print("WARNING: git diff failed — no git repo or no changes", file=sys.stderr)
        return {"error": "git diff failed", "note": "not a git repo or no changes"}

    if not changed_files:
        return {"note": "no uncommitted changes"}

    all_results = []
    for f in changed_files:
        r = impact_from_code(mappings, f, use_crg)
        if "error" not in r:
            all_results.append(r)

    return {
        "query_type": "diff→spec",
        "changed_files": changed_files,
        "results": all_results,
    }


def main():
    parser = argparse.ArgumentParser(description="CRG + .trace-mapping.yaml 影響分析")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--spec-id", type=str, help="影響分析: 仕様IDからコード影響")
    group.add_argument("--file", type=str, help="影響分析: コードファイルから仕様影響")
    group.add_argument("--diff", action="store_true", help="影響分析: git diff から")
    group.add_argument("--list", action="store_true", help="全マッピング一覧")
    parser.add_argument("--crg", action="store_true", help="CRG (code-review-graph) ツールと連携")
    parser.add_argument("--crg-hook", type=str, help="CRG クエリ用の外部スクリプト（デフォルト: $CRG_HOOK または crg-query CLI）")
    parser.add_argument("--json", action="store_true", help="JSON 出力")
    args = parser.parse_args()

    # --crg-hook が指定された場合、環境変数 CRG_HOOK に設定
    if args.crg_hook:
        os.environ["CRG_HOOK"] = args.crg_hook

    mappings = load_mapping()

    result: dict[str, Any] = {}

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


def _print_human(result: dict):
    """人間可読な形式で出力する。"""
    if "error" in result:
        print(f"❌ {result['error']}")
        if "note" in result:
            print(f"   {result['note']}")
        return

    if "note" in result:
        print(f"ℹ️  {result['note']}")
        return

    if "mapping_count" in result:
        print(f"📋 Total mappings: {result['mapping_count']}")
        for m in result["mappings"]:
            print(f"  [{m['id']}] {m.get('description', '(no description)')}")
            for f in m.get("code", {}).get("files", []):
                print(f"    → {f}")
        return

    qtype = result.get("query_type", "")

    if qtype == "spec→code":
        print(f"🔍 Spec {result['spec_id']} → Code Impact")
        print(f"  Files ({len(result['files'])}):")
        for f in result["files"]:
            print(f"    📄 {f}")
        print(f"  Symbols ({len(result['symbols'])}):")
        for s in result["symbols"]:
            print(f"    🔧 {s}")
        print(f"  Tasks ({len(result['tasks'])}):")
        for t in result["tasks"]:
            print(f"    📋 {t}")
        print(f"  Docs ({len(result['docs'])}):")
        for d in result["docs"]:
            print(f"    📝 {d}")
        if "crg_impact" in result:
            print(f"\n  CRG Impact:")
            for ci in result["crg_impact"]:
                print(f"    {ci['symbol']}: {ci['crg_result']}")

    elif qtype == "code→spec":
        print(f"🔍 {result['file']} → Spec Impact")
        print(f"  Requirements ({len(result['affected_requirements'])}):")
        for r in result["affected_requirements"]:
            print(f"    📋 {r}")
        print(f"  Tasks ({len(result['affected_tasks'])}):")
        for t in result["affected_tasks"]:
            print(f"    📋 {t}")
        print(f"  Design sections ({len(result['affected_design_sections'])}):")
        for d in result["affected_design_sections"]:
            print(f"    📝 {d}")
        print(f"  Spec files:")
        for s in result["affected_specs"]:
            print(f"    📄 {s}")

    elif qtype == "diff→spec":
        print(f"🔍 git diff → Spec Impact")
        print(f"  Changed files ({len(result['changed_files'])}):")
        for f in result["changed_files"]:
            print(f"    📄 {f}")
        for r in result.get("results", []):
            print(f"\n  --- {r.get('file', 'unknown')} ---")
            print(f"    Requirements: {', '.join(r.get('affected_requirements', []))}")
            print(f"    Tasks: {', '.join(r.get('affected_tasks', []))}")


if __name__ == "__main__":
    main()
