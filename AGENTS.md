# AGENTS.md — Coding Agent Instructions for `flood-safe-routing`

This repository implements **Flood-Safe Routing**, a 24-hour Hackathon real-time flood detection and dynamic rerouting Web App built on the **Google Tech Stack**:
- **AI Vision:** `Gemini 3.8 Flash` (`google-genai` Python SDK, Multimodal Structured Outputs)
- **Maps & Rerouting:** `Google Maps Platform` (`Maps JavaScript API` + `Routes API v2`)
- **Real-time State & Storage:** `Firebase` (`Cloud Firestore` + `Storage`) / `Google Cloud`

All coding agents operating in this repository MUST read and obey the contracts, invariants, and verification steps below.

---

## 1. Mandatory Reading Order Before Editing Code

1. `docs/api-and-data-contract.md` — Canonical REST API, Firestore collection schemas, and Gemini output schema. **Never rename or drop fields without updating this file first.**
2. Module-specific deep technical references in `docs/references/`:
   - `docs/references/gemini-vision-flood-detection.md` — `google-genai` SDK patterns, Pydantic `response_schema`, `response.parsed`, Vietnamese visual flood rubric.
   - `docs/references/google-routes-dynamic-rerouting.md` — `Routes API v2` headers/constraints, `TWO_WHEELER` mode, two-layer polyline intersection & `via` detour waypoint math.
   - `docs/references/maps-js-and-firebase-realtime.md` — `@vis.gl/react-google-maps`, `HeatmapLayer`, Firebase v10 modular `onSnapshot`, automatic live rerouting hooks.
   - `docs/references/traffic-camera-ingestion-and-repro.md` — Vietnamese traffic camera realities (`camera.0511.vn`, HCMC portal), multi-adapter frame extraction, frame-diff throttling.
3. `CONTRIBUTING.md` — Team ownership boundaries (`frontend/`, `backend/`, `ai-vision/`, `data/`).

---

## 2. Module Ownership & Workspace Map

| Directory | Runtime / Stack | Primary Responsibility |
| :--- | :--- | :--- |
| `frontend/` | React 18 + Vite + TS + `@vis.gl/react-google-maps` + `firebase` v10 | Map UI, red flood circles, `HeatmapLayer`, Firestore `onSnapshot`, crowdsourcing modal, live reroute display |
| `backend/` | Python 3.11+ + FastAPI + `firebase-admin` + `httpx` + `polyline` | REST API (`:8000`), `Routes API v2` two-layer avoidance, Firestore read/write, camera polling orchestration |
| `ai-vision/` | Python 3.11+ + `google-genai` + `pydantic` + `Pillow` | Frame extraction (`camera_extractor.py`) and Gemini Vision structured severity analysis (`analyzer.py`) |
| `data/` | JSON / GeoJSON | Sample camera metadata, sample active flood events, historical flood heatmap seed records |
| `tests/` & `scripts/` | Python `unittest` & CLI tools | Deterministic unit tests, contract validation, and reproducible diagnostic scripts |

---

## 3. Hard Engineering Invariants & Pitfall Guards

1. **Preserve `USE_MOCK_FALLBACK=true` Support Everywhere:**
   - Every external integration (Gemini API, Google Maps/Routes API, Firebase Firestore) MUST fall back cleanly to deterministic mock/sample behavior when `USE_MOCK_FALLBACK=true` and live credentials are absent. Teammates must be able to boot and test every module offline or before keys arrive.
2. **Never Hardcode AI Flood Verdicts:**
   - Real images and video frames must always be routed through `analyze_flood_image()` (`google-genai` when live key is present). Mock fallback is strictly for missing credentials or unit tests.
3. **Never Fetch External Traffic Camera Feeds From Browser (`frontend/`):**
   - Public Vietnamese portals (`camera.0511.vn`, `giaothong.hochiminhcity.gov.vn`) block CORS, rotate session tokens, or restrict access. Always fetch/ingest camera frames from backend workers (`ai-vision/src/camera_extractor.py`) via sanctioned adapters (`http_snapshot`, `local_video`, or `crowdsourcing_upload`). Never attempt auth bypass or destructive scraping.
4. **Google Routes API v2 Critical Constraints:**
   - ALWAYS send `X-Goog-FieldMask` (without it, `computeRoutes` fails).
   - NEVER set `computeAlternativeRoutes: true` together with `intermediates` (Routes API ignores alternatives when `intermediates` is present).
   - NEVER set `"optimizeWaypointOrder": true` when any intermediate waypoint has `"via": true` (Routes API rejects the request).
   - NEVER double-nest `intermediates[].location.location` — use `{"location": {"latLng": {"latitude": ..., "longitude": ...}}, "via": true}`.
5. **Model Configuration Flexibility:**
   - Always read the Gemini model name from `os.getenv("GEMINI_MODEL", "gemini-3.8-flash")` instead of scattering hardcoded model strings across files.
6. **Protect Secrets:**
   - Never commit `.env` or `serviceAccountKey.json` (both are ignored in `.gitignore`). Never print API keys or tokens in logs.

---

## 4. Reproducible Verification Commands

Run these commands from the repository root after making changes:

```bash
# 1. Check runtime, JSON data integrity, and Live vs Mock mode
python scripts/check_env.py

# 2. Run deterministic unit & contract tests (no paid API keys required)
python -m unittest discover -s tests -v

# 3. Reproduce routing intersection & detour calculation against sample flood data
python scripts/repro_routing.py

# 4. Reproduce AI flood analysis (uses Gemini live if GEMINI_API_KEY is set, else Mock Fallback)
python scripts/repro_gemini_vision.py

# 5. Reproduce camera/frame ingestion check
python scripts/repro_camera_fetch.py
```

For FastAPI local server verification:
```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
```
For Frontend local build/typecheck verification:
```bash
cd frontend && npm install && npm run build
```
