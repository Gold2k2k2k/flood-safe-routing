"""
Environment & Project Readiness Checker for Flood-Safe Routing.
Run from repository root:
    python scripts/check_env.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv_simple(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def is_real_key(val: str | None) -> bool:
    if not val:
        return False
    lower = val.lower()
    return not (
        lower.startswith("your_")
        or "example" in lower
        or "placeholder" in lower
        or val == ""
    )


def check_runtime() -> bool:
    print("=== 1. Runtime Check ===")
    py_ver = sys.version.split()[0]
    print(f"[OK] Python version: {py_ver}")

    node_bin = shutil.which("node")
    if node_bin:
        try:
            node_ver = subprocess.check_output(
                [node_bin, "--version"], text=True, timeout=5
            ).strip()
            print(f"[OK] Node.js version: {node_ver}")
        except Exception as exc:
            print(f"[WARN] Could not query node version: {exc}")
    else:
        print("[WARN] Node.js not found in PATH (needed for frontend/).")
    return True


def check_structure_and_data() -> bool:
    print("\n=== 2. Required Contracts, Agent Docs & Sample Data ===")
    required_files = [
        ROOT_DIR / "AGENTS.md",
        ROOT_DIR / "docs" / "api-and-data-contract.md",
        ROOT_DIR / "frontend" / "src" / "vite-env.d.ts",
        ROOT_DIR / "frontend" / "src" / "types" / "flood.ts",
    ]
    all_ok = True
    for rf in required_files:
        if rf.exists():
            print(f"[OK] {rf.relative_to(ROOT_DIR)}")
        else:
            print(f"[FAIL] Missing required file: {rf.relative_to(ROOT_DIR)}")
            all_ok = False

    sample_files = [
        ROOT_DIR / "data" / "cameras.sample.json",
        ROOT_DIR / "data" / "flood_events.sample.geojson",
        ROOT_DIR / "data" / "heatmap_history.sample.json",
    ]
    for fp in sample_files:
        if not fp.exists():
            print(f"[FAIL] Missing sample file: {fp.relative_to(ROOT_DIR)}")
            all_ok = False
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            count = (
                len(data.get("features", []))
                if isinstance(data, dict)
                else (len(data) if isinstance(data, list) else 0)
            )
            print(f"[OK] {fp.relative_to(ROOT_DIR)} (valid JSON, {count} records)")
        except Exception as exc:
            print(f"[FAIL] Invalid JSON in {fp.relative_to(ROOT_DIR)}: {exc}")
            all_ok = False
    return all_ok


def check_env_config() -> None:
    print("\n=== 3. Environment & Google Tech Stack Status ===")
    env_file = ROOT_DIR / ".env"
    if not env_file.exists():
        print("[INFO] .env file not found. Using defaults from .env.example (MOCK FALLBACK active).")
        env_vars = load_dotenv_simple(ROOT_DIR / ".env.example")
    else:
        print("[OK] Found .env file.")
        env_vars = load_dotenv_simple(env_file)

    merged = {**env_vars, **os.environ}
    mock_fallback = merged.get("USE_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")
    gemini_model = merged.get("GEMINI_MODEL", "gemini-3.8-flash")
    has_gemini = is_real_key(merged.get("GEMINI_API_KEY"))
    has_maps = is_real_key(merged.get("GOOGLE_MAPS_API_KEY")) or is_real_key(
        merged.get("VITE_GOOGLE_MAPS_API_KEY")
    )
    sa_rel = merged.get("GOOGLE_APPLICATION_CREDENTIALS", "serviceAccountKey.json")
    sa_path = Path(sa_rel)
    if not sa_path.is_absolute():
        sa_path = (ROOT_DIR / sa_path).resolve()
    has_firebase = sa_path.exists() and is_real_key(merged.get("FIREBASE_PROJECT_ID"))

    print(f"  - USE_MOCK_FALLBACK : {mock_fallback}")
    print(f"  - GEMINI_MODEL      : {gemini_model}")
    print(
        f"  - Gemini Vision API : {'LIVE KEY CONFIGURED' if has_gemini else 'MOCK FALLBACK MODE'}"
    )
    print(
        f"  - Google Maps/Routes: {'LIVE KEY CONFIGURED' if has_maps else 'MOCK FALLBACK MODE'}"
    )
    print(
        f"  - Firebase Firestore: {'LIVE CONFIGURED' if has_firebase else 'MOCK FALLBACK MODE (reads data/*.sample.*)'}"
    )


def main() -> int:
    print("Flood-Safe Routing — Contributor Environment Check\n")
    ok_runtime = check_runtime()
    ok_data = check_structure_and_data()
    check_env_config()

    if ok_runtime and ok_data:
        print("\n[READY] Workspace is healthy and ready for development!")
        return 0
    print("\n[ERROR] Some checks failed. Please review messages above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
