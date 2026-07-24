#!/usr/bin/env python3
"""check_drift.py — コードと仕様書の間のドリフト（乖離）を検出する。

スナップショットベースで動作し、コードの @impl タグと .trace-mapping.yaml を比較する。

Usage:
  # 現在の状態のスナップショットを保存
  python3 .agents/scripts/check_drift.py --snapshot

  # 現在の状態とスナップショットを比較（ドリフト検出）
  python3 .agents/scripts/check_drift.py --check

  # git diff ベースでドリフト検出
  python3 .agents/scripts/check_drift.py --diff

  # git diff ベース + CI ゲートモード（ドリフトあり → exit 1）
  python3 .agents/scripts/check_drift.py --diff --gate

  # ベースブランチとの比較
  python3 .agents/scripts/check_drift.py --diff --base origin/main
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml


TRACE_MAPPING_PATH = Path(".trace-mapping.yaml")
SNAPSHOT_PATH = Path(".trace-snapshot.json")

# このスクリプト自身のディレクトリ（.agents/scripts/）は extract_tags.py と同じ
_SCRIPT_DIR = Path(__file__).parent.resolve()
_EXTRACT_TAGS = _SCRIPT_DIR / "extract_tags.py"


def load_mapping(path: Path = TRACE_MAPPING_PATH) -> list[dict]:
    """.trace-mapping.yaml を読み込む。"""
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("mappings", [])


def extract_tags_from_dir(directory: str = ".") -> list[dict]:
    """.agents/scripts/extract_tags.py を使ってタグを抽出する。"""
    extractor = _EXTRACT_TAGS
    if not extractor.exists():
        print(f"WARNING: {extractor} not found", file=sys.stderr)
        return []
    try:
        result = subprocess.run(
            [sys.executable, str(extractor), "--dir", directory, "--format", "json"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"WARNING: extract_tags failed: {e}", file=sys.stderr)
        return []


def compute_file_hash(filepath: str) -> Optional[str]:
    """ファイルの SHA256 ハッシュを計算する。"""
    path = Path(filepath)
    if not path.exists():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def build_snapshot(mappings: list[dict]) -> dict:
    """現状のスナップショットを構築する。

    スナップショットには以下を含む:
    - 各マッピングのコードファイルのハッシュ
    - コード内の @impl タグの抽出結果
    """
    snapshot: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "files": {},
        "tag_entries": [],
    }

    # 各マッピングのコードファイルのハッシュ
    for m in mappings:
        for f in m.get("code", {}).get("files", []):
            fpath = str(Path(f).resolve())
            fhash = compute_file_hash(fpath)
            snapshot["files"][fpath] = {
                "hash": fhash,
                "mapping_id": m["id"],
            }

    # コード内の @impl タグ
    tags = extract_tags_from_dir()
    snapshot["tag_entries"] = tags

    return snapshot


def save_snapshot(snapshot: dict):
    """スナップショットを保存する。"""
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"✅ Snapshot saved: {SNAPSHOT_PATH} ({len(snapshot['files'])} files, {len(snapshot['tag_entries'])} tags)")


def load_snapshot(path: Path = SNAPSHOT_PATH) -> Optional[dict]:
    """スナップショットを読み込む。"""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def detect_drift(mappings: list[dict], snapshot: dict) -> list[dict]:
    """現在の状態とスナップショットを比較し、ドリフトを検出する。"""
    findings: list[dict] = []

    # 1. ファイルハッシュの変化をチェック
    for fpath, snap_info in snapshot.get("files", {}).items():
        current_hash = compute_file_hash(fpath)
        if current_hash is None:
            findings.append({
                "type": "FILE_DELETED",
                "file": fpath,
                "mapping_id": snap_info["mapping_id"],
                "detail": f"File was deleted since snapshot ({snap_info.get('hash', '?')[:12]})",
            })
        elif current_hash != snap_info["hash"]:
            findings.append({
                "type": "FILE_CHANGED",
                "file": fpath,
                "mapping_id": snap_info["mapping_id"],
                "detail": f"File content changed (hash: {current_hash[:12]} vs {snap_info.get('hash', '?')[:12]})",
            })

    # 2. 新しい @impl タグの追加をチェック（.trace-mapping.yaml に未登録）
    current_tags = extract_tags_from_dir()
    registered_ids = {m["id"] for m in mappings}

    for tag in current_tags:
        if tag["tag"] == "impl":
            values = [v.strip() for v in tag["value"].split(",")]
            for v in values:
                if v and v not in registered_ids:
                    findings.append({
                        "type": "UNREGISTERED_IMPL_TAG",
                        "file": tag["file"],
                        "tag": v,
                        "detail": f"@impl {v} in {tag['file']} not found in .trace-mapping.yaml",
                    })

    # 3. .trace-mapping.yaml にあるがコードにない @impl タグ
    tag_map: dict[str, list[str]] = {}
    for tag in current_tags:
        if tag["tag"] == "impl":
            tag_map.setdefault(tag["file"], [])
            tag_map[tag["file"]].extend(v.strip() for v in tag["value"].split(","))

    for m in mappings:
        for code_file in m.get("code", {}).get("files", []):
            resolved = str(Path(code_file).resolve())
            file_tags = tag_map.get(resolved, [])
            if m["id"] not in file_tags:
                # 違うファイルでタグされてる可能性もある
                all_files_with_tag = [
                    f for f, ids in tag_map.items()
                    if m["id"] in ids
                ]
                if not all_files_with_tag:
                    findings.append({
                        "type": "MISSING_IMPL_TAG",
                        "file": code_file,
                        "mapping_id": m["id"],
                        "detail": f"@impl {m['id']} expected in {code_file} but not found in any file",
                    })

    return findings


def check_diff(base: Optional[str] = None, gate: bool = False) -> list[dict]:
    """git diff ベースでドリフトを検出する。"""
    findings: list[dict] = []

    try:
        # 変更ファイル一覧を取得
        if base:
            cmd = ["git", "diff", "--name-only", base]
        else:
            cmd = ["git", "diff", "--name-only"]
        diff_result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        changed_files = [f for f in diff_result.stdout.strip().split("\n") if f]
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git diff failed: {e}", file=sys.stderr)
        return [{"type": "GIT_ERROR", "detail": str(e)}]

    if not changed_files:
        return findings

    # 各変更ファイルがどの spec に影響するか
    mappings = load_mapping()
    for f in changed_files:
        for m in mappings:
            if f in m.get("code", {}).get("files", []):
                findings.append({
                    "type": "CODE_CHANGED_AFFECTS_SPEC",
                    "file": f,
                    "mapping_id": m["id"],
                    "spec": m.get("spec", ""),
                    "detail": f"Change in {f} may affect spec [{m['id']}]: {m.get('spec', '')}",
                })

    if gate and findings:
        print(f"\n❌ DRIFT DETECTED ({len(findings)} findings) — gate failed")
        for f in findings:
            print(f"  [{f['type']}] {f['detail']}")
        sys.exit(1)

    return findings


def main():
    parser = argparse.ArgumentParser(description="コードと仕様書のドリフト検出")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", action="store_true", help="現在の状態のスナップショットを保存")
    group.add_argument("--check", action="store_true", help="現在の状態とスナップショットを比較")
    group.add_argument("--diff", action="store_true", help="git diff ベースでドリフト検出")
    parser.add_argument("--base", type=str, help="差分比較のベースブランチ（--diff と併用）")
    parser.add_argument("--gate", action="store_true", help="CI ゲートモード（--diff と併用、ドリフトあり → exit 1）")
    args = parser.parse_args()

    mappings = load_mapping()
    if not mappings:
        print("WARNING: .trace-mapping.yaml not found or empty", file=sys.stderr)

    if args.snapshot:
        snapshot = build_snapshot(mappings)
        save_snapshot(snapshot)
        sys.exit(0)

    if args.check:
        snapshot = load_snapshot()
        if snapshot is None:
            print("ERROR: No snapshot found. Run --snapshot first.", file=sys.stderr)
            sys.exit(1)
        findings = detect_drift(mappings, snapshot)
        if findings:
            print(f"❌ {len(findings)} drift(s) detected:")
            for f in findings:
                print(f"  [{f['type']}] {f['detail']}")
            sys.exit(1)
        else:
            print("✅ No drift detected — code and specs are in sync.")
            sys.exit(0)

    if args.diff:
        findings = check_diff(args.base, args.gate)
        if findings:
            print(f"\n📋 {len(findings)} change(s) with spec impact:")
            for f in findings:
                print(f"  [{f['type']}] {f['detail']}")
        else:
            print("✅ No spec-impacting changes detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
