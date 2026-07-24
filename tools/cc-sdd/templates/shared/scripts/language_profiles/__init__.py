"""language_profiles loader — 言語プロファイルを読み込む

使い方:
    from language_profiles import load_profile
    profile = load_profile()
    EXTENSIONS = profile["extensions"]
    TEST_PATTERNS = profile["test_patterns"]
    EXCLUDE_DIRS = profile["exclude_dirs"]
"""

import os
import yaml
from pathlib import Path

_PROFILE_DIR = Path(__file__).parent.resolve()
_DEFAULT_PROFILE = _PROFILE_DIR / "default.yaml"


def load_profile(name: str = "default") -> dict:
    """言語プロファイルを読み込む。

    Args:
        name: プロファイル名（"default" またはカスタムYAMLのファイル名）

    Returns:
        {
            "extensions": {".py": "Python", ...},
            "comment_styles": ["#", "//"],
            "test_patterns": ["**/test_*.py", ...],
            "exclude_dirs": {".git", "node_modules", ...},
        }
    """
    # プロファイルファイルを探す
    search_order = [
        _PROFILE_DIR / f"{name}.yaml",
        _PROFILE_DIR / f"{name}.yml",
        _DEFAULT_PROFILE,
    ]
    if name != "default":
        # カスタムプロファイルは .kiro/profiles/ も探す
        for base in [Path.cwd() / ".kiro" / "profiles",
                     Path(os.environ.get("HOME", "/tmp")) / ".config" / "cc-sdd-graph" / "profiles"]:
            search_order.insert(0, base / f"{name}.yaml")
            search_order.insert(1, base / f"{name}.yml")

    profile_path = None
    for p in search_order:
        if p.exists():
            profile_path = p
            break

    if not profile_path:
        raise FileNotFoundError(
            f"Profile '{name}' not found. Searched: {search_order}"
        )

    with open(profile_path) as f:
        raw = yaml.safe_load(f)

    if not raw or "builtin" not in raw:
        data = raw if raw else {}
    else:
        data = raw["builtin"]

    # 整形して返す
    return {
        "extensions": data.get("extensions", {}),
        "comment_styles": data.get("comment_styles", ["#", "//"]),
        "test_patterns": data.get("test_file_patterns", []),
        "exclude_dirs": set(data.get("exclude_dirs", [])),
    }


# モジュール初期化時にデフォルトプロファイルをロード
_default_profile: dict = {}
try:
    _default_profile = load_profile("default")
except Exception:
    pass


def get_extensions() -> set[str]:
    return set(_default_profile.get("extensions", {}).keys())


def get_test_patterns() -> list[str]:
    return _default_profile.get("test_patterns", [])


def get_comment_styles() -> list[str]:
    return _default_profile.get("comment_styles", ["#", "//"])


def get_exclude_dirs() -> set[str]:
    return _default_profile.get("exclude_dirs", set())
