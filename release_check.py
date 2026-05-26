from __future__ import annotations

import importlib
import json
from pathlib import Path


REQUIRED_IMPORTS = [
    "PySide6",
    "cv2",
    "numpy",
]

REQUIRED_PROJECT_FILES = [
    "app_qt.py",
    "config.json",
    "database.py",
    "file_manager.py",
    "logging_config.py",
]

REQUIRED_OUTPUT_DIRS = [
    "output",
]


def check_imports() -> list[str]:
    messages = []
    for module_name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
            messages.append(f"[OK] import {module_name}")
        except Exception as exc:
            messages.append(f"[FAIL] import {module_name}: {exc}")
    return messages


def check_project_files(root: Path) -> list[str]:
    messages = []
    for rel in REQUIRED_PROJECT_FILES:
        path = root / rel
        if path.exists():
            messages.append(f"[OK] file {rel}")
        else:
            messages.append(f"[FAIL] missing file {rel}")
    return messages


def check_output_dirs(root: Path) -> list[str]:
    messages = []
    for rel in REQUIRED_OUTPUT_DIRS:
        path = root / rel
        if path.exists() and path.is_dir():
            messages.append(f"[OK] dir {rel}")
        else:
            messages.append(f"[WARN] dir {rel} not found")
    return messages


def check_config(root: Path) -> list[str]:
    messages = []
    config_path = root / "config.json"
    if not config_path.exists():
        messages.append("[FAIL] config.json not found")
        return messages

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        messages.append("[OK] config.json readable")
    except Exception as exc:
        messages.append(f"[FAIL] config.json invalid JSON: {exc}")
        return messages

    for key in ["paths", "recording", "analysis", "cameras"]:
        if key in payload:
            messages.append(f"[OK] config key '{key}'")
        else:
            messages.append(f"[WARN] config key '{key}' missing")

    return messages


def main() -> int:
    root = Path(__file__).resolve().parent

    checks = []
    checks.extend(check_imports())
    checks.extend(check_project_files(root))
    checks.extend(check_output_dirs(root))
    checks.extend(check_config(root))

    print("=== LAP2GO Release Check ===")
    for line in checks:
        print(line)

    has_fail = any(line.startswith("[FAIL]") for line in checks)
    return 1 if has_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())