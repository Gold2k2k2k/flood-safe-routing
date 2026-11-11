"""Backend configuration and environment flags."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")


def _has_real_value(val: str | None) -> bool:
    if not val:
        return False
    lower = val.lower()
    return not (lower.startswith("your_") or "placeholder" in lower or "example" in lower)


class Settings:
    PORT: int = int(os.getenv("PORT", "8000"))
    USE_MOCK_FALLBACK: bool = os.getenv("USE_MOCK_FALLBACK", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", str(ROOT_DIR / "serviceAccountKey.json")
    )

    @property
    def gemini_configured(self) -> bool:
        return _has_real_value(self.GEMINI_API_KEY)

    @property
    def google_maps_configured(self) -> bool:
        return _has_real_value(self.GOOGLE_MAPS_API_KEY)

    @property
    def firebase_configured(self) -> bool:
        sa_file = Path(self.GOOGLE_APPLICATION_CREDENTIALS)
        if not sa_file.is_absolute():
            sa_file = ROOT_DIR / sa_file
        return sa_file.exists() and _has_real_value(self.FIREBASE_PROJECT_ID)


settings = Settings()
