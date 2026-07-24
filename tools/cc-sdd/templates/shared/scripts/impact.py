#!/usr/bin/env python3
"""
impact.py — CRG (code-review-graph) + .trace-mapping.yaml による影響分析。
--quick モードでは .trace-mapping.yaml なしでも @impl/@spec/@verifies タグの
grep で簡易影響分析が可能。

影響度バンド（Green/Amber/Gray）で各成果物の関連強度を分類:
  🟢 GREEN  (≥50点): 強い証拠（.trace-mapping + @impl + テスト等）— 自動通過OK
  🟡 AMBER  (≥20点): 中程度の証拠 — 要レビュー
  ⚪ GRAY   (<20点): 弱い証拠 — 参考情報

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

  # --band: バンドフィルターで結果を絞り込み
  python3 .agents/scripts/impact.py --spec-id 1.1 --band green
  python3 .agents/scripts/impact.py --quick --diff --band amber+

  # --graph: 対話的HTMLグラフを生成
  python3 .agents/scripts/impact.py --list --graph
  python3 .agents/scripts/impact.py --spec-id 1.1 --graph trace-1.1.html
  python3 .agents/scripts/impact.py --quick --diff --graph

  # --serve: ブラウザで対話的グラフを表示
  python3 .agents/scripts/impact.py --list --serve
  python3 .agents/scripts/impact.py --spec-id 1.1 --serve
"""

import argparse
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

import yaml


TRACE_MAPPING_PATH = Path(".trace-mapping.yaml")

# タグパターン（extract_tags.py と同一）
# @impl, @verifies は数値ID（1.1, 1.2）のみ、@module/@feature は任意文字列
IMPL_TAG_RE = re.compile(r'#\s*@impl\s+([\d.]+(?:\s*,\s*[\d.]+)*)', re.MULTILINE)
VERIFIES_TAG_RE = re.compile(r'#\s*@verifies\s+([\d.]+(?:\s*,\s*[\d.]+)*)', re.MULTILINE)
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

# ── 影響度バンド（Green/Amber/Gray） ──
# 証拠タイプごとの重み
BAND_WEIGHTS = {
    "mapping": 40,         # .trace-mapping.yaml に直接記載
    "impl_tag": 25,        # @impl タグ
    "verifies_tag": 20,    # @verifies タグ
    "crg_direct": 15,      # CRG 1 hop（直接 import/呼び出し）
    "crg_transitive": 5,   # CRG 2+ hops（推移的依存）
    "grep": 10,            # --quick grep でタグマッチ
    "snapshot": 10,        # スナップショットと一致
}

# バンド閾値
BAND_GREEN_MIN = 50   # ≥50 → green
BAND_AMBER_MIN = 20   # ≥20 → amber（未満 → gray）


def _compute_file_band(
    file_path: str,
    spec_id: str,
    in_mapping: bool = False,
    has_impl: bool = False,
    has_verifies: bool = False,
    crg_hops: Optional[int] = None,
    quick_mode: bool = False,
) -> dict:
    """1ファイルの影響度バンドを計算する。

    Args:
        file_path: 評価対象のファイルパス
        spec_id: 対象要件ID
        in_mapping: .trace-mapping.yaml に記載されているか
        has_impl: @impl タグが一致するか
        has_verifies: @verifies タグが一致するか
        crg_hops: CRG 推移的距離（None = 未計測）
        quick_mode: --quick grep モードか

    Returns:
        {"band": "green"|"amber"|"gray", "score": int, "evidence": list[dict]}
    """
    score = 0
    evidence = []

    if in_mapping:
        score += BAND_WEIGHTS["mapping"]
        evidence.append({"type": "mapping", "weight": BAND_WEIGHTS["mapping"],
                         "detail": ".trace-mapping.yaml"})
    if has_impl:
        score += BAND_WEIGHTS["impl_tag"]
        evidence.append({"type": "impl_tag", "weight": BAND_WEIGHTS["impl_tag"],
                         "detail": f"@impl {spec_id}"})
    if has_verifies:
        score += BAND_WEIGHTS["verifies_tag"]
        evidence.append({"type": "verifies_tag", "weight": BAND_WEIGHTS["verifies_tag"],
                         "detail": f"@verifies {spec_id}"})
    if crg_hops is not None:
        if crg_hops <= 1:
            score += BAND_WEIGHTS["crg_direct"]
            evidence.append({"type": "crg_direct", "weight": BAND_WEIGHTS["crg_direct"],
                             "detail": f"CRG {crg_hops} hop(s)"})
        else:
            score += BAND_WEIGHTS["crg_transitive"]
            evidence.append({"type": "crg_transitive", "weight": BAND_WEIGHTS["crg_transitive"],
                             "detail": f"CRG {crg_hops} hops"})
    if quick_mode:
        score += BAND_WEIGHTS["grep"]
        evidence.append({"type": "grep", "weight": BAND_WEIGHTS["grep"],
                         "detail": "grep match"})

    if score >= BAND_GREEN_MIN:
        band = "green"
    elif score >= BAND_AMBER_MIN:
        band = "amber"
    else:
        band = "gray"

    return {"band": band, "score": score, "evidence": evidence}


def _check_file_has_tag(file_path: Path, tag_re: re.Pattern, spec_id: str) -> bool:
    """ファイルに指定タグと要件IDのペアが含まれているか確認する。"""
    try:
        content = file_path.read_text(encoding="utf-8")
        for match in tag_re.finditer(content):
            values = [v.strip() for v in match.group(1).replace("\uff0c", ",").split(",") if v.strip()]
            if spec_id in values:
                return True
    except (UnicodeDecodeError, OSError):
        pass
    return False


def _is_test_file(file_path: str) -> bool:
    """ファイルパスがテストファイルパターンに一致するか。"""
    from fnmatch import fnmatch
    for pattern in TEST_FILE_PATTERNS:
        if fnmatch(file_path, pattern):
            return True
    return False


def _build_banded(files: list[str], spec_id: str, project_dir: Path,
                  mapping_files: set[str] = set(),
                  use_crg: bool = False, quick_mode: bool = False) -> dict:
    """ファイルリストからバンド情報を構築する。

    Returns:
        {"green": [...], "amber": [...], "gray": [...], "summary": {...}}
    """
    banded: dict[str, list[dict]] = {"green": [], "amber": [], "gray": []}

    for f in files:
        fpath = Path(f) if f.startswith("/") else project_dir / f
        in_mapping = f in mapping_files

        # @impl / @verifies チェック（ファイルが存在する場合のみ）
        has_impl = _check_file_has_tag(fpath, IMPL_TAG_RE, spec_id) if fpath.exists() else False
        has_verifies = _check_file_has_tag(fpath, VERIFIES_TAG_RE, spec_id) if fpath.exists() else False

        band_info = _compute_file_band(
            file_path=f,
            spec_id=spec_id,
            in_mapping=in_mapping,
            has_impl=has_impl,
            has_verifies=has_verifies,
            quick_mode=quick_mode,
        )

        band_info["file"] = f
        banded[band_info["band"]].append(band_info)

    return {
        "green": banded["green"],
        "amber": banded["amber"],
        "gray": banded["gray"],
        "summary": {"green": len(banded["green"]),
                     "amber": len(banded["amber"]),
                     "gray": len(banded["gray"])},
    }


def _filter_by_band(banded: dict, band_filter: str) -> list[str]:
    """--band フィルターに基づいてファイルリストを絞り込む。"""
    if band_filter == "green":
        return [e["file"] for e in banded.get("green", [])]
    elif band_filter == "amber":
        return [e["file"] for e in banded.get("amber", [])]
    elif band_filter == "gray":
        return [e["file"] for e in banded.get("gray", [])]
    elif band_filter == "green+":
        return ([e["file"] for e in banded.get("green", [])] +
                [e["file"] for e in banded.get("amber", [])])
    elif band_filter == "amber+":
        return ([e["file"] for e in banded.get("amber", [])] +
                [e["file"] for e in banded.get("gray", [])])
    return []


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


def impact_from_spec(mappings: list[dict], spec_id: str, use_crg: bool = False,
                     project_dir: Optional[Path] = None) -> dict:
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

    # バンド情報を追加（project_dir があれば）
    if project_dir:
        mapping_files = set(result["files"])
        result["banded"] = _build_banded(
            files=result["files"],
            spec_id=spec_id,
            project_dir=project_dir,
            mapping_files=mapping_files,
            use_crg=use_crg,
        )
        result["band_summary"] = result["banded"]["summary"]

    return result


def impact_from_code(mappings: list[dict], filepath: str, use_crg: bool = False,
                     project_dir: Optional[Path] = None) -> dict:
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

    # バンド情報（code→spec ではファイル→要件のため spec_id は複数）
    if project_dir:
        banded_reqs: dict[str, list[dict]] = {"green": [], "amber": [], "gray": []}
        for req in result["affected_requirements"]:
            fpath = project_dir / filepath
            has_impl = _check_file_has_tag(fpath, IMPL_TAG_RE, req) if fpath.exists() else False
            band_info = _compute_file_band(
                file_path=filepath,
                spec_id=req,
                in_mapping=True,
                has_impl=has_impl,
            )
            band_info["requirement"] = req
            banded_reqs[band_info["band"]].append(band_info)
        result["banded"] = banded_reqs
        result["band_summary"] = {
            "green": len(banded_reqs["green"]),
            "amber": len(banded_reqs["amber"]),
            "gray": len(banded_reqs["gray"]),
        }

    return result


def impact_from_diff(mappings: list[dict], use_crg: bool = False,
                     project_dir: Optional[Path] = None) -> dict:
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
        r = impact_from_code(mappings, f, use_crg, project_dir=project_dir)
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

    # バンド情報（quick モード）
    banded: dict[str, list[dict]] = {"green": [], "amber": [], "gray": []}
    for rid in impl_ids:
        # 対象ファイル自身のバンド
        self_band = _compute_file_band(
            file_path=rel, spec_id=rid, has_impl=True, quick_mode=True)
        self_band["rid"] = rid
        banded[self_band["band"]].append(self_band)

        # 関連コードファイルのバンド（grep のみ）
        for codef in related["related_impl_files"].get(rid, []):
            code_band = _compute_file_band(
                file_path=codef, spec_id=rid, quick_mode=True)
            code_band["rid"] = rid
            code_band["file"] = codef
            banded[code_band["band"]].append(code_band)

        # テストファイルのバンド（verifies + grep）
        for testf in related["related_tests"].get(rid, []):
            test_band = _compute_file_band(
                file_path=testf, spec_id=rid, has_verifies=True, quick_mode=True)
            test_band["rid"] = rid
            test_band["file"] = testf
            banded[test_band["band"]].append(test_band)

        # 仕様書のバンド（grep のみ）
        for specf in related["related_specs"].get(rid, []):
            spec_band = _compute_file_band(
                file_path=specf, spec_id=rid, quick_mode=True)
            spec_band["rid"] = rid
            spec_band["file"] = specf
            banded[spec_band["band"]].append(spec_band)

    related["banded"] = banded
    related["band_summary"] = {
        "green": len(banded["green"]),
        "amber": len(banded["amber"]),
        "gray": len(banded["gray"]),
    }

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

        # バンド情報
        all_files = result["impl_files"] + result["test_files"] + result["spec_files"] + result["design_files"]
        banded = _build_banded(
            files=list(set(all_files)),
            spec_id=spec_id,
            project_dir=project_dir,
            quick_mode=True,
        )
        result["banded"] = banded
        result["band_summary"] = banded["summary"]
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


# ── Rename モード（要件IDの一括書き換え） ──


def _make_id_re(id_str: str) -> re.Pattern:
    """要件ID（例: 1.1）をスタンドアロントークンとしてマッチする正規表現。
    1.1 が 1.10 や 11.1 の一部としてマッチしないよう境界を設定する。"""
    escaped = re.escape(id_str)
    return re.compile(rf'(?<!\d){escaped}(?!\.?\d)')


def cmd_rename(project_dir: Path, old_id: str, new_id: str, dry_run: bool = False) -> dict:
    """
    --rename OLD NEW: プロジェクト内の全ファイルで要件IDを一括書き換え。
    dry-run モードでは変更せずにプレビュー表示。
    """
    id_re = _make_id_re(old_id)

    # 各ファイル種別のスキャン定義: (glob_pattern, replacement logic description)
    # ファイルを収集してから内容を書き換える
    changes: list[dict] = []

    def _scan_and_replace(filepath: Path, label: str, content_transform) -> None:
        nonlocal changes
        try:
            content = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return
        new_content = content_transform(content)
        if new_content != content:
            rel = str(filepath.relative_to(project_dir)) if filepath.is_relative_to(project_dir) else str(filepath)
            changes.append({"file": rel, "label": label})
            if not dry_run:
                filepath.write_text(new_content)

    # 1. コードファイル: @impl OLD → @impl NEW
    code_suffixes = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".rb", ".java", ".kt", ".swift")
    for suffix in code_suffixes:
        for fpath in sorted(project_dir.rglob(f"*{suffix}")):
            if any(part in EXCLUDE_DIRS for part in fpath.parts):
                continue
            _scan_and_replace(fpath, "@impl", lambda c: id_re.sub(new_id, c))

    # 2. テストファイル: @verifies OLD → @verifies NEW
    # （テストファイルはコードファイルと同じ拡張子の一部なので重複スキャンになるが、
    #  id_re 置換は冪等なので問題ない）
    test_suffixes = tuple(
        sorted(set(p.split("*")[-1] for p in TEST_FILE_PATTERNS if p.endswith(".*")))
    )
    # test_suffixes は code_suffixes の部分集合なのでスキップ可だが、
    # 分かりやすさのため別ラベルで再度スキャンしても安全

    # 3. .md ファイル: @spec OLD / @satisfies OLD
    for fpath in sorted(project_dir.rglob("*.md")):
        if any(part in EXCLUDE_DIRS for part in fpath.parts):
            continue
        _scan_and_replace(fpath, "@spec/@satisfies", lambda c: id_re.sub(new_id, c))

    # 4. tasks.md: _Requirements: OLD_ / _Depends: OLD_
    for fpath in sorted(project_dir.rglob("tasks.md")):
        if any(part in EXCLUDE_DIRS for part in fpath.parts):
            continue
        _scan_and_replace(fpath, "_Requirements_/_Depends_", lambda c: id_re.sub(new_id, c))

    # 5. .trace-mapping.yaml: id: "OLD" → id: "NEW"
    mapping_path = project_dir / TRACE_MAPPING_PATH
    if mapping_path.exists():
        def _replace_mapping_id(content: str) -> str:
            # id: "OLD" → id: "NEW" （YAML内の id フィールドのみ）
            return re.sub(
                rf'id:\s*"{old_id}"',
                f'id: "{new_id}"',
                content,
            )
        _scan_and_replace(mapping_path, "id: in .trace-mapping.yaml", _replace_mapping_id)

    return {
        "query_type": "rename",
        "old_id": old_id,
        "new_id": new_id,
        "dry_run": dry_run,
        "changes": changes,
        "total": len(changes),
    }


# ── メイン ──


def _print_band_entry(entry: dict, indent: str = "    ") -> None:
    """1エントリのバンド表示（スコア付き）。"""
    band_icon = {"green": "\U0001f7e2", "amber": "\U0001f7e1", "gray": "\u26aa"}
    icon = band_icon.get(entry.get("band", ""), "\u26aa")
    score = entry.get("score", 0)
    file_path = entry.get("file", entry.get("requirement", ""))
    evidence_str = " + ".join(
        f"{e['type']}:{e['weight']}" for e in entry.get("evidence", [])
    )
    if evidence_str:
        print(f"{indent}{icon} {file_path}  ({evidence_str} = {score})")
    else:
        print(f"{indent}{icon} {file_path}")


def _print_banded(banded: dict, spec_id: str) -> None:
    """バンド別に分類された結果を表示する。"""
    labels = {
        "green": ("GREEN", "auto-approve"),
        "amber": ("AMBER", "review required"),
        "gray": ("GRAY", "reference only"),
    }
    icons = {"green": "\U0001f7e2", "amber": "\U0001f7e1", "gray": "\u26aa"}

    for band_key in ("green", "amber", "gray"):
        entries = banded.get(band_key, [])
        if not entries:
            continue
        label, note = labels.get(band_key, ("", ""))
        icon = icons.get(band_key, "")
        print(f"\n{icon} {label} ({note}) — {len(entries)} item(s)")
        for entry in entries:
            _print_band_entry(entry)


def _print_quick_rid(result: dict, rid: str) -> None:
    """Quick モードの個別要件ID表示（後方互換）。"""
    impls = result.get("related_impl_files", {}).get(rid, [])
    tests = result.get("related_tests", {}).get(rid, [])
    specs = result.get("related_specs", {}).get(rid, [])
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


def _print_quick_spec(result: dict) -> None:
    """Quick モード spec→code 表示（後方互換）。"""
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


def _print_std_spec(result: dict) -> None:
    """標準モード spec→code 表示（後方互換）。"""
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


def _print_std_code(result: dict) -> None:
    """標準モード code→spec 表示（後方互換）。"""
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


def _print_std_diff(result: dict) -> None:
    """標準モード diff 表示（後方互換）。"""
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


def _print_rename(result: dict) -> None:
    """Rename モード表示。"""
    mode = " (dry-run)" if result.get("dry_run") else ""
    print(f"\U0001f4dd Rename{mode}: {result['old_id']} \u2192 {result['new_id']}")
    print(f"  Total: {result['total']} file(s)")
    for ch in result.get("changes", []):
        print(f"    \u270f\ufe0f {ch['file']}  ({ch['label']})")
    if result.get("dry_run") and result["total"] > 0:
        print()
        print("  Run without --dry-run to apply changes.")


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

    # ── バンドサマリー（あれば常に表示） ──
    band_summary = result.get("band_summary")
    if band_summary:
        total = band_summary["green"] + band_summary["amber"] + band_summary["gray"]
        parts = []
        if band_summary["green"]:
            parts.append(f"\U0001f7e2 {band_summary['green']}")
        if band_summary["amber"]:
            parts.append(f"\U0001f7e1 {band_summary['amber']}")
        if band_summary["gray"]:
            parts.append(f"\u26aa {band_summary['gray']}")
        print(f"  Band: {'  '.join(parts)}  (total {total})")
        print()

    # ── バンド別表示 ──
    banded = result.get("banded")
    if banded:
        _print_banded(banded, result.get("spec_id", ""))

    # ── Quick モード（後方互換） ──
    if qtype == "quick-file" and not banded:
        print(f"\U0001f50d Quick Impact: {result['file']}")
        print(f"  @impl tags: {', '.join(result['impl_tags'])}")
        for rid in result["impl_tags"]:
            _print_quick_rid(result, rid)

    if qtype == "quick-spec" and not banded:
        print(f"\U0001f50d Quick Impact: spec-id {result['spec_id']}")
        _print_quick_spec(result)

    if qtype == "quick-diff" and not banded:
        print(f"\U0001f50d Quick Impact: git diff")
        print(f"  Changed files ({len(result['changed_files'])}):")
        for f in result["changed_files"]:
            print(f"    \U0001f4c4 {f}")
        for r in result.get("results", []):
            if r.get("impl_tags"):
                print(f"  \u2192 {r['file']}:")
                print(f"     @impl tags: {', '.join(r['impl_tags'])}")

    # ── 標準モード（後方互換） ──
    if qtype == "spec\u2192code" and not banded:
        _print_std_spec(result)

    elif qtype == "code\u2192spec" and not banded:
        _print_std_code(result)

    elif qtype == "diff\u2192spec" and not banded:
        _print_std_diff(result)

    # ── Rename モード ──
    if qtype == "rename":
        _print_rename(result)


# ── グラフ可視化 ──


def _gather_graph_data(mappings: list[dict], result: dict) -> dict:
    """マッピングと分析結果からグラフデータ（nodes, edges）を構築する。"""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    node_id_counter: int = 0

    def _add_node(label: str, group: str, file_path: str = "",
                  band: str = "") -> str:
        nonlocal node_id_counter
        nid = f"n{node_id_counter}"
        node_id_counter += 1

        colors = {
            "spec": {"bg": "#4a90d9", "border": "#2c5f9e", "text": "#fff"},
            "code": {"bg": "#50b86c", "border": "#2e7d46", "text": "#fff"},
            "test": {"bg": "#e8a838", "border": "#b57c1e", "text": "#fff"},
            "design": {"bg": "#9b59b6", "border": "#6c3483", "text": "#fff"},
            "task": {"bg": "#e67e22", "border": "#a85d16", "text": "#fff"},
        }
        band_bg = {"green": "#2ecc71", "amber": "#f39c12", "gray": "#95a5a6"}

        c = colors.get(group, colors["spec"])
        bg = band_bg.get(band, c["bg"])

        if band:
            title = f"<b>{label}</b><br/>band: {band}<br/>{file_path}"
        elif file_path:
            title = f"<b>{label}</b><br/>{file_path}"
        else:
            title = f"<b>{label}</b>"

        nodes.append({
            "id": nid,
            "label": label if len(label) < 40 else label[:37] + "...",
            "title": title,
            "group": group,
            "color": {"background": bg, "border": c["border"]},
            "font": {"color": c["text"], "size": 14},
            "shape": "box",
            "physics": True,
        })
        return nid

    # 全マッピングからノードを構築
    for m in mappings:
        mid = m.get("id", "")
        spec_paths = m.get("spec", [])
        code_files = m.get("code", {}).get("files", [])
        symbols = m.get("code", {}).get("symbols", [])
        tasks = m.get("tasks", [])
        docs = m.get("docs", [])

        if spec_paths:
            spec_path = spec_paths[0] if isinstance(spec_paths, list) else spec_paths
        else:
            spec_path = ""

        spec_nid = _add_node(f"Req {mid}", "spec", spec_path)

        for cf in code_files:
            cf_label = Path(cf).stem
            band = ""
            if result and "banded" in result:
                for entry in (result["banded"].get("green", []) +
                              result["banded"].get("amber", []) +
                              result["banded"].get("gray", [])):
                    if entry.get("file") and cf in entry["file"]:
                        band = entry.get("band", "")
                        break
            cf_nid = _add_node(cf_label, "code", cf, band)
            edges.append({"from": spec_nid, "to": cf_nid,
                          "label": "@impl", "color": "#50b86c",
                          "width": 2, "dashes": False})

        for sym in symbols:
            sym_nid = _add_node(sym[:30], "code", f"symbol: {sym}")
            edges.append({"from": spec_nid, "to": sym_nid,
                          "label": "symbol", "color": "#50b86c",
                          "width": 1, "dashes": True})

        for task in tasks:
            task_nid = _add_node(str(task), "task")
            edges.append({"from": spec_nid, "to": task_nid,
                          "label": "task", "color": "#e67e22",
                          "width": 1, "dashes": False})

        for doc in docs:
            doc_label = Path(doc).stem if doc else "doc"
            doc_nid = _add_node(doc_label, "design", doc)
            edges.append({"from": spec_nid, "to": doc_nid,
                          "label": "doc", "color": "#9b59b6",
                          "width": 1, "dashes": True})

    return {"nodes": nodes, "edges": edges}


def _render_graph_html(graph_data: dict, title: str) -> str:
    """グラフデータを自己完結型HTML（外部依存なし）にレンダリングする。"""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    # 単純な力指向レイアウトをPythonで計算
    import math
    pos = _compute_force_layout(nodes, edges)

    # SVG サイズ
    W, H = 1200, 800
    PAD = 60

    # 座標を SVG 空間にマッピング（ラベル幅を考慮したパディング）
    # はみ出さないようにレイアウトを再調整
    pos2 = _compute_force_layout(nodes, edges, width=W, height=H)
    max_label_w = max((len(n.get("label", "")) * 7.5 + 20) for n in nodes) if nodes else 100
    margin = max(max_label_w / 2 + 20, 90)
    for nid, (px, py) in pos2.items():
        pos2[nid] = (min(max(px, margin), W - margin),
                     min(max(py, margin * 0.4), H - margin * 0.4))
    pos = pos2

    # レイアウト座標を直接SVG座標として使う

    def to_svg(nid: str) -> tuple[float, float]:
        return pos.get(nid, (W / 2, H / 2))

    group_colors = {
        "spec": {"fill": "#4a90d9", "stroke": "#2c5f9e", "text": "#fff"},
        "code": {"fill": "#50b86c", "stroke": "#2e7d46", "text": "#fff"},
        "test": {"fill": "#e8a838", "stroke": "#b57c1e", "text": "#fff"},
        "design": {"fill": "#9b59b6", "stroke": "#6c3483", "text": "#fff"},
        "task": {"fill": "#e67e22", "stroke": "#a85d16", "text": "#fff"},
    }
    band_colors = {"green": "#2ecc71", "amber": "#f39c12", "gray": "#95a5a6"}

    # SVG エレメント生成
    def _node_color(n: dict) -> str:
        band = n.get("band", "")
        return band_colors.get(band, group_colors.get(n.get("group", "spec"), {}).get("fill", "#666"))

    def _node_label(n: dict) -> str:
        lbl = n.get("label", "?")
        return lbl[:30] + "..." if len(lbl) > 30 else lbl

    # SVG ビルド
    svg_nodes: list[str] = []
    svg_edges: list[str] = []

    for e in edges:
        frm, to = e.get("from"), e.get("to")
        if frm not in pos or to not in pos:
            continue
        x1, y1 = to_svg(frm)
        x2, y2 = to_svg(to)
        label = e.get("label", "")
        svg_edges.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="#555" stroke-width="2" marker-end="url(#arrow)"/>'
        )
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 8
            svg_edges.append(
                f'<text x="{mx:.0f}" y="{my:.0f}" fill="#888" font-size="10" '
                f'text-anchor="middle">{label}</text>'
            )

    for n in nodes:
        nid = n.get("id", "")
        if nid not in pos:
            continue
        x, y = to_svg(nid)
        color = _node_color(n)
        grp = n.get("group", "spec")
        gc = group_colors.get(grp, group_colors["spec"])
        bw = 2 if n.get("band") else 1
        label = _node_label(n)
        title = n.get("title", "").replace('"', "'")
        w = max(len(label) * 7.5, 60)
        h = 28
        rx, ry = 4, 4

        svg_nodes.append(
            f'<g class="node" data-id="{nid}" data-title="{title}" '
            f'data-band="{n.get("band", "")}" data-group="{grp}">'
            f'<rect x="{x - w / 2:.0f}" y="{y - h / 2:.0f}" width="{w:.0f}" '
            f'height="{h:.0f}" rx="{rx}" ry="{ry}" '
            f'fill="{color}" stroke="{gc["stroke"]}" stroke-width="{bw}" '
            f'style="cursor:pointer"/>'
            f'<text x="{x:.0f}" y="{y + 5:.0f}" fill="{gc["text"]}" '
            f'font-size="12" text-anchor="middle" style="pointer-events:none">'
            f'{label}</text></g>'
        )

    nodes_json = json.dumps(nodes, ensure_ascii=False)
    edges_json = json.dumps(edges, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Traceability Graph</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
         background:#1a1a2e; color:#e0e0e0; }}
  #toolbar {{ position:fixed; top:0; left:0; right:0; z-index:100;
              background:rgba(26,26,46,0.95); padding:10px 20px;
              display:flex; align-items:center; gap:12px;
              border-bottom:1px solid #333; backdrop-filter:blur(8px); }}
  #toolbar h1 {{ font-size:16px; font-weight:600; white-space:nowrap; }}
  #toolbar .badge {{ font-size:11px; padding:2px 8px; border-radius:10px;
                     background:#333; color:#aaa; }}
  #toolbar input {{ flex:1; max-width:300px; padding:6px 12px; border:1px solid #444;
                    border-radius:6px; background:#16213e; color:#e0e0e0;
                    font-size:13px; outline:none; }}
  #toolbar input:focus {{ border-color:#4a90d9; }}
  #toolbar .legend {{ display:flex; gap:16px; font-size:12px; margin-left:auto; }}
  .legend-item {{ display:flex; align-items:center; gap:4px; }}
  .legend-dot {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
  #graph-container {{ position:fixed; top:52px; left:0; right:0; bottom:0; overflow:hidden; }}
  #graph-container svg {{ width:100%; height:100%; }}
  .node:hover rect {{ filter:brightness(1.3); }}
  #tooltip {{ position:fixed; display:none; z-index:200;
              background:rgba(0,0,0,0.85); color:#fff; padding:8px 12px;
              border-radius:6px; font-size:12px; max-width:400px;
              border:1px solid #444; pointer-events:none; }}
  #stats {{ position:fixed; bottom:12px; right:16px; z-index:100;
            font-size:11px; color:#666; background:rgba(26,26,46,0.8);
            padding:4px 10px; border-radius:6px; }}
</style>
</head>
<body>
<div id="toolbar">
  <h1>{title}</h1>
  <span class="badge" id="nodeCount">{len(nodes)} nodes</span>
  <span class="badge" id="edgeCount">{len(edges)} edges</span>
  <input id="search" type="text" placeholder="Search nodes..." oninput="filterGraph(this.value)">
  <div class="legend">
    <span class="legend-item"><span class="legend-dot" style="background:#4a90d9"></span> Spec</span>
    <span class="legend-item"><span class="legend-dot" style="background:#50b86c"></span> Code</span>
    <span class="legend-item"><span class="legend-dot" style="background:#e8a838"></span> Test</span>
    <span class="legend-item"><span class="legend-dot" style="background:#9b59b6"></span> Design</span>
    <span class="legend-item"><span class="legend-dot" style="background:#e67e22"></span> Task</span>
  </div>
</div>
<div id="graph-container">
<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5"
    markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10" fill="#555"/></marker></defs>
  <rect width="{W}" height="{H}" fill="transparent"/>
  {"".join(svg_edges)}
  {"".join(svg_nodes)}
</svg>
</div>
<div id="tooltip"></div>
<div id="stats">SVG • hover to inspect • drag to explore</div>

<script>
(function() {{
const nodes = {nodes_json};
const edges = {edges_json};

// Search filter
document.getElementById('search').addEventListener('input', function() {{
  const q = this.value.toLowerCase();
  document.querySelectorAll('.node').forEach(g => {{
    const label = g.querySelector('text')?.textContent?.toLowerCase() || '';
    const title = (g.dataset.title || '').toLowerCase();
    g.style.display = (label.includes(q) || title.includes(q)) ? '' : 'none';
  }});
}});

// Hover tooltip
document.querySelectorAll('.node').forEach(g => {{
  g.addEventListener('mouseenter', function(e) {{
    const title = this.dataset.title || this.querySelector('text')?.textContent || '';
    const tip = document.getElementById('tooltip');
    tip.textContent = title.replace(/<br\\s*\\/?>/gi, ' · ').replace(/<\\/?[^>]+>/g, '');
    tip.style.display = 'block';
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY - 10) + 'px';
  }});
  g.addEventListener('mousemove', function(e) {{
    const tip = document.getElementById('tooltip');
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY - 10) + 'px';
  }});
  g.addEventListener('mouseleave', function() {{
    document.getElementById('tooltip').style.display = 'none';
  }});
}});

// Keyboard: Escape clears search
document.addEventListener('keydown', function(e) {{
  if (e.key === 'Escape') {{
    document.getElementById('search').value = '';
    document.getElementById('search').dispatchEvent(new Event('input'));
  }}
}});

// SVG pan/zoom via mouse drag
let isPanning = false, panStart = {{x:0,y:0}}, panOffset = {{x:0,y:0}};
const svg = document.querySelector('svg');
const viewbox = svg.viewBox.baseVal;
svg.addEventListener('mousedown', function(e) {{
  if (e.target.tagName === 'rect' || e.target.tagName === 'text') return;
  isPanning = true;
  panStart.x = e.clientX;
  panStart.y = e.clientY;
}});
window.addEventListener('mousemove', function(e) {{
  if (!isPanning) return;
  const dx = panStart.x - e.clientX;
  const dy = panStart.y - e.clientY;
  viewbox.x += dx;
  viewbox.y += dy;
  panStart.x = e.clientX;
  panStart.y = e.clientY;
}});
window.addEventListener('mouseup', function() {{ isPanning = false; }});
svg.addEventListener('wheel', function(e) {{
  e.preventDefault();
  const scale = e.deltaY > 0 ? 1.1 : 0.9;
  const cx = viewbox.x + viewbox.width / 2;
  const cy = viewbox.y + viewbox.height / 2;
  viewbox.width = Math.max(100, Math.min(5000, viewbox.width * scale));
  viewbox.height = Math.max(100, Math.min(5000, viewbox.height * scale));
  viewbox.x = cx - viewbox.width / 2;
  viewbox.y = cy - viewbox.height / 2;
}});
}})();
</script>
</body>
</html>"""


def _compute_force_layout(nodes: list[dict], edges: list[dict],
                          iterations: int = 300, width: float = 1200,
                          height: float = 800) -> dict[str, tuple[float, float]]:
    """階層レイアウトを計算する。Specノードが上、コードが下、テスト・設計が横。"""
    import math

    pos: dict[str, tuple[float, float]] = {}
    node_ids = [n["id"] for n in nodes]

    if not node_ids:
        return {}

    # ノード種別でグループ化
    spec_nodes: list[str] = []
    code_nodes: list[str] = []
    test_nodes: list[str] = []
    design_nodes: list[str] = []
    task_nodes: list[str] = []

    for n in nodes:
        nid = n["id"]
        grp = n.get("group", "")
        if grp == "spec":
            spec_nodes.append(nid)
        elif grp == "code":
            code_nodes.append(nid)
        elif grp == "test":
            test_nodes.append(nid)
        elif grp == "design":
            design_nodes.append(nid)
        elif grp == "task":
            task_nodes.append(nid)

    def _arrange(nids: list[str], y: float, margin: float = 120) -> None:
        if not nids:
            return
        count = len(nids)
        if count == 1:
            pos[nids[0]] = (width / 2, y)
        else:
            spacing = min((width - 2 * margin) / (count - 1), 220)
            total_w = spacing * (count - 1)
            start_x = (width - total_w) / 2
            for i, nid in enumerate(nids):
                pos[nid] = (start_x + i * spacing, y)

    _arrange(spec_nodes, height * 0.15)
    _arrange(code_nodes, height * 0.40)
    _arrange(test_nodes, height * 0.58)

    # 設計・タスクはコードの左右に
    design_x = width * 0.05
    task_x = width * 0.85
    for i, nid in enumerate(design_nodes):
        pos[nid] = (design_x, height * 0.40 + i * 60)
    for i, nid in enumerate(task_nodes):
        pos[nid] = (task_x, height * 0.40 + i * 60)

    # 未分類は下に
    unplaced = [nid for nid in node_ids if nid not in pos]
    _arrange(unplaced, height * 0.75)

    return pos


def cmd_graph(mappings: list[dict], result: dict, output_path: str = "trace-graph.html",
              spec_id: str = "") -> str:
    """対話的HTMLグラフを生成する。"""
    graph_data = _gather_graph_data(mappings, result)
    title = f"Traceability: {spec_id}" if spec_id else "Traceability Graph"
    html = _render_graph_html(graph_data, title)
    out = Path(output_path)
    out.write_text(html, encoding="utf-8")
    print(f"\n✅ Graph saved: {out.resolve()}")
    print(f"   Open in browser: file://{out.resolve()}")
    return str(out.resolve())


def cmd_serve(mappings: list[dict], result: dict, port: int = 0,
              spec_id: str = "") -> None:
    """対話的グラフをHTTPサーバで起動しブラウザを開く。"""
    graph_data = _gather_graph_data(mappings, result)
    title = f"Traceability: {spec_id}" if spec_id else "Traceability Graph"
    html = _render_graph_html(graph_data, title)

    import tempfile
    tmp = Path(tempfile.mkstemp(suffix=".html")[1])
    tmp.write_text(html, encoding="utf-8")

    if port == 0:
        with socketserver.TCPServer(("", 0), http.server.SimpleHTTPRequestHandler) as s:
            port = s.server_address[1]

    output_path = tmp.resolve()
    print(f"\n✅ Serving graph at http://localhost:{port}")
    print(f"   (temp: {output_path})")
    print("   Press Ctrl+C to stop\n")

    webbrowser.open(f"http://localhost:{port}/{tmp.name}")

    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped")


def main():
    parser = argparse.ArgumentParser(description="CRG + .trace-mapping.yaml 影響分析、または --quick 簡易影響分析")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--spec-id", type=str, help="影響分析: 仕様IDからコード影響")
    group.add_argument("--file", type=str, help="影響分析: コードファイルから仕様影響")
    group.add_argument("--diff", action="store_true", help="影響分析: git diff から")
    group.add_argument("--list", action="store_true", help="全マッピング一覧")
    group.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"),
                       help="要件IDの一括書き換え（例: --rename 1.1 2.1）。--dry-run でプレビュー")
    parser.add_argument("--dry-run", action="store_true", help="--rename の変更をプレビュー（実際には書き換えない）")
    parser.add_argument("--crg", action="store_true", help="CRG (code-review-graph) ツールと連携")
    parser.add_argument("--crg-hook", type=str, help="CRG クエリ用の外部スクリプト")
    parser.add_argument("--json", action="store_true", help="JSON 出力")
    parser.add_argument("--quick", action="store_true", help=".trace-mapping.yaml 不要の簡易モード（@impl/@spec/@verifies を grep）")
    parser.add_argument("--band", type=str,
                        choices=["green", "amber", "gray", "green+", "amber+"],
                        help="バンドフィルター（green/amber/gray/green+/amber+）。指定したバンド以上の項目のみ表示")
    parser.add_argument("--project-dir", type=str, default=".",
                        help="プロジェクトルート（--quick モード用、デフォルト: カレント）")
    parser.add_argument("--graph", nargs="?", const="trace-graph.html", default=None,
                        metavar="FILE",
                        help="対話的HTMLグラフを生成（--list / --spec-id / --file と併用）。"
                             "ファイル名指定可（デフォルト: trace-graph.html）")
    parser.add_argument("--serve", action="store_true",
                        help="対話的グラフをHTTPサーバで起動しブラウザで開く")
    args = parser.parse_args()

    if args.crg_hook:
        os.environ["CRG_HOOK"] = args.crg_hook

    project_dir = Path(args.project_dir).resolve()

    result: dict[str, Any] = {}

    # Rename モード（--rename が指定された場合）
    if args.rename:
        old_id, new_id = args.rename
        if old_id == new_id:
            result = {"error": "OLD and NEW IDs are the same", "query_type": "rename"}
        else:
            result = cmd_rename(project_dir, old_id, new_id, args.dry_run)
    elif args.quick:
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
            result = impact_from_spec(mappings, args.spec_id, args.crg, project_dir=project_dir)
        elif args.file:
            result = impact_from_code(mappings, args.file, args.crg, project_dir=project_dir)
        elif args.diff:
            result = impact_from_diff(mappings, args.crg, project_dir=project_dir)

    # --band フィルターが指定された場合、バンドで絞り込み
    if args.band and "banded" in result:
        filtered_files = _filter_by_band(result["banded"], args.band)
        result["files"] = filtered_files
        filtered_summary = {"green": 0, "amber": 0, "gray": 0}
        for band_key in filtered_summary:
            filtered_summary[band_key] = len(result["banded"].get(band_key, []))
        result["band_summary"] = filtered_summary

    # グラフモード（--graph / --serve）
    if args.graph is not None or args.serve:
        # マッピングデータを取得（結果になければ --list 相当で取得）
        if "mappings" in result:
            mappings = result["mappings"]
        elif "mapping" in result:
            mappings = [result["mapping"]]
        else:
            mappings = load_mapping(project_dir / TRACE_MAPPING_PATH)
            if not mappings:
                # quick モードの場合は空グラフ
                mappings = []

        spec_id = result.get("spec_id", args.spec_id or "")

        if args.serve:
            cmd_serve(mappings, result, spec_id=spec_id)
            return
        else:
            output_path = args.graph if args.graph else "trace-graph.html"
            cmd_graph(mappings, result, output_path, spec_id=spec_id)
            return

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result)


if __name__ == "__main__":
    main()
