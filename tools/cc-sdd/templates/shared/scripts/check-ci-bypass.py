#!/usr/bin/env python3
"""
check-ci-bypass.py — P0-4: CI gate bypass detection

CIゲートが正しく機能しているか、またはバイパスされた変更がないかを確認する。

チェック内容:
  1. pre-push hook の設置確認（.git/hooks/pre-push が存在し有効か）
  2. 直近のコミットログに SKIP_TRACE の使用履歴がないか
  3. GitHub Actions の workflow 実行履歴（gh CLI があれば）

Exit code: 0 = all checks pass, 1 = issues found

Usage:
  python3 .agents/scripts/check-ci-bypass.py
  python3 .agents/scripts/check-ci-bypass.py --json
  python3 .agents/scripts/check-ci-bypass.py --verbose

環境変数:
  SKIP_TRACE_ALLOWED=1    bypass を許可（エラーにしない）
  CI_BYPASS_LOOKBACK=<N>  確認する直近日数（デフォルト: 14）
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def check_prepush_hook(project_dir: Path) -> list[str]:
    """Check 1: pre-push hook が正しく設置されているか。"""
    issues = []
    hook_path = project_dir / ".git" / "hooks" / "pre-push"

    if not hook_path.exists():
        issues.append(
            "[hook] pre-push hook が未設置 — トレーサビリティゲートがプッシュ時に実行されない"
        )
        issues.append(
            "[hook] 設定: ln -sf ../../.agents/scripts/pre-push.sh .git/hooks/pre-push"
        )
        return issues

    if not os.access(hook_path, os.X_OK):
        issues.append(
            f"[hook] pre-push hook ({hook_path}) に実行権限がない"
        )
        return issues

    # 内容チェック — 我々の pre-push.sh を指しているか
    try:
        content = hook_path.read_text(encoding="utf-8")
        if "pre-push.sh" not in content and "ci-check.sh" not in content:
            issues.append(
                "[hook] pre-push hook が存在するが、cc-sdd-graph のスクリプトを"
                "参照していない（別の hook で上書きされている可能性）"
            )
    except (UnicodeDecodeError, OSError):
        issues.append(f"[hook] pre-push hook ({hook_path}) が読み取れない")

    return issues


def check_skip_trace_in_git_log(project_dir: Path, lookback_days: int) -> list[str]:
    """Check 2: 直近のコミットログに SKIP_TRACE の使用がないか。"""
    issues = []

    try:
        since = f"--since={lookback_days}.days"
        result = subprocess.run(
            ["git", "log", since, "--oneline", "--grep=SKIP_TRACE"],
            capture_output=True, text=True, cwd=project_dir,
        )
        if result.stdout.strip():
            lines = result.stdout.strip().split("\n")
            issues.append(
                f"[skip] 直近{lookback_days}日間に SKIP_TRACE でのプッシュが "
                f"{len(lines)} 件見つかりました"
            )
            for line in lines[:5]:
                issues.append(f"  [skip]  {line}")
            if len(lines) > 5:
                issues.append(f"  [skip]  ... and {len(lines)-5} more")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # git 管理下でなければスキップ

    return issues


def check_github_actions_status(project_dir: Path, lookback_days: int) -> list[str]:
    """Check 3: GitHub Actions の直近ワークフロー実行履歴（gh CLI が必要）。"""
    issues = []

    # gh CLI の有無
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []  # gh CLI なし → スキップ（opt-in）

    # リポジトリ情報
    try:
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, cwd=project_dir,
        ).stdout.strip()
        # "git@github.com:owner/repo.git" や "https://github.com/owner/repo" から
        # owner/repo を抽出
        repo_match = re.search(r'(?:github\.com[:\/])([^\/]+\/[^\/\.]+?)(?:\.git)?$', remote)
        if not repo_match:
            return []
        repo = repo_match.group(1)
    except subprocess.CalledProcessError:
        return []

    # 直近の workflow run を取得
    try:
        since = f"--since={lookback_days}.days"
        result = subprocess.run(
            ["gh", "run", "list",
             "--repo", repo,
             "--workflow=traceability-check.yml",
             "--limit=10",
             "--json=conclusion,displayTitle,createdAt,url"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []

        runs = json.loads(result.stdout) if result.stdout.strip() else []

        if not runs:
            issues.append(
                "[ci] 直近{lookback_days}日間に traceability-check CI の実行記録なし"
                " — CI が正しく設定されているか確認してください"
            )
            return issues

        # 失敗した run をチェック
        failed_runs = [r for r in runs if r.get("conclusion") == "failure"]
        if failed_runs:
            for run in failed_runs[:3]:
                issues.append(
                    f"[ci] ❌ CI 失敗: {run.get('displayTitle', 'unknown')} "
                    f"({run.get('createdAt', '?')}) — {run.get('url', '')}"
                )
            if len(failed_runs) > 3:
                issues.append(f"  [ci]  ... and {len(failed_runs)-3} more failures")

        # スキップされた run をチェック
        skipped_runs = [r for r in runs if r.get("conclusion") == "skipped"]
        if skipped_runs:
            issues.append(
                f"[ci] ⚠️ 直近{lookback_days}日間で {len(skipped_runs)} 件の CI が "
                f"スキップされました"
            )

    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass

    return issues


def main():
    parser = argparse.ArgumentParser(
        description="P0-4: CI gate bypass detection"
    )
    parser.add_argument("--json", action="store_true", help="JSON 出力")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細出力（正常なチェックも表示）")
    parser.add_argument("--project-dir", type=str, default=".",
                        help="プロジェクトルート（デフォルト: カレント）")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    lookback_days = int(os.environ.get("CI_BYPASS_LOOKBACK", "14"))
    skip_allowed = os.environ.get("SKIP_TRACE_ALLOWED", "0") == "1"

    all_issues = []

    # Check 1: pre-push hook
    hook_issues = check_prepush_hook(project_dir)
    all_issues.extend(hook_issues)

    # Check 2: SKIP_TRACE in git log
    log_issues = check_skip_trace_in_git_log(project_dir, lookback_days)
    all_issues.extend(log_issues)

    # Check 3: GitHub Actions
    ci_issues = check_github_actions_status(project_dir, lookback_days)
    all_issues.extend(ci_issues)

    if args.json:
        result = {
            "check": "ci_gate_bypassed",
            "lookback_days": lookback_days,
            "skip_allowed": skip_allowed,
            "issues": all_issues,
            "passed": len(all_issues) == 0,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    # Human-readable output
    if args.verbose:
        print("=== P0-4: CI Gate Bypass Detection ===\n")

    if not all_issues:
        if args.verbose:
            print("  ✅ pre-push hook: 設置済み")
            print("  ✅ git log: SKIP_TRACE 使用なし")
            print("  ✅ GitHub Actions: CI 正常稼働")
        print("\n✅ P0-4: CI gate bypass not detected — 全チェック通過")
        sys.exit(0)
    else:
        print(f"\n⚠️  P0-4: {len(all_issues)} 件の課題")
        for issue in all_issues:
            print(f"  ❌ {issue}")

        if skip_allowed:
            print("\n  （SKIP_TRACE_ALLOWED=1 のためエラーにはしません）")
            sys.exit(0)
        else:
            print("\n  SKIP_TRACE_ALLOWED=1 でバイパスを許可できます")
            sys.exit(1)


if __name__ == "__main__":
    main()
