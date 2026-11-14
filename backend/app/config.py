"""Backend configuration, path resolution, and environment flags."""

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
    @property
    def PORT(self) -> int:
        return int(os.getenv("PORT", "8000"))

    @property
    def USE_MOCK_FALLBACK(self) -> bool:
        return os.getenv("USE_MOCK_FALLBACK", "true").lower() in ("true", "1", "yes")

    @property
    def GEMINI_API_KEY(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")

    @property
    def GEMINI_MODEL(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    @property
    def AI_VISION_URL(self) -> str:
        return os.getenv("AI_VISION_URL", "").strip()

    @property
    def GOOGLE_MAPS_API_KEY(self) -> str:
        return os.getenv("GOOGLE_MAPS_API_KEY", "")

    @property
    def FIREBASE_PROJECT_ID(self) -> str:
        return os.getenv("FIREBASE_PROJECT_ID", "")

    @property
    def GOOGLE_APPLICATION_CREDENTIALS(self) -> str:
        return os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "./serviceAccountKey.json")

    @property
    def FIREBASE_SERVICE_ACCOUNT_JSON(self) -> str:
        return os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()

    @property
    def FLOOD_ALERT_THRESHOLD(self) -> float:
        return float(os.getenv("FLOOD_ALERT_THRESHOLD", "0.65"))

    @property
    def CAMERA_POLL_INTERVAL_SECONDS(self) -> int:
        return int(os.getenv("CAMERA_POLL_INTERVAL_SECONDS", "30"))

    @property
    def FLOOD_ZONE_TTL_MINUTES(self) -> int:
        return int(os.getenv("FLOOD_ZONE_TTL_MINUTES", "15"))

    @property
    def resolved_credentials_path(self) -> Path:
        sa_file = Path(self.GOOGLE_APPLICATION_CREDENTIALS)
        if not sa_file.is_absolute():
            sa_file = (ROOT_DIR / sa_file).resolve()
        return sa_file

    @property
    def gemini_configured(self) -> bool:
        return _has_real_value(self.GEMINI_API_KEY)

    @property
    def google_maps_configured(self) -> bool:
        return _has_real_value(self.GOOGLE_MAPS_API_KEY)

    @property
    def firebase_configured(self) -> bool:
        has_creds = self.resolved_credentials_path.exists() or _has_real_value(
            self.FIREBASE_SERVICE_ACCOUNT_JSON
        )
        return has_creds and _has_real_value(self.FIREBASE_PROJECT_ID)


settings = Settings()
