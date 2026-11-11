# Deep Reference: Vietnamese Traffic Camera Ingestion & Reproducible Demo Streams

This document summarizes technical research on public Vietnamese municipal camera portals and defines a reliable, compliant ingestion architecture for `ai-vision/src/camera_extractor.py`.

---

## 1. Realities of Public Vietnamese Traffic Camera Portals

Research into **`camera.0511.vn`** (Da Nang) and **`giaothong.hochiminhcity.gov.vn`** (Ho Chi Minh City) reveals four critical engineering constraints:

1. **No Official Open Developer API:** Neither portal publishes a documented REST, RTSP, or HLS developer API with guaranteed uptime or SLA.
2. **Strict Browser CORS & Tokenization:** Stream and snapshot URLs behind municipal web maps rely on internal dynamic tokens, session cookies, or `.aspx`/`.ashx` proxy handlers and enforce CORS policies that block direct browser `fetch()` calls.
3. **Intermittent Public Access / IP Limits:** `camera.0511.vn` periodically restricts public feeds during maintenance or upgrades, and municipal gateways may throttle or geo-filter non-Vietnam IPs (e.g., cloud servers outside `asia-southeast1`).
4. **Sunny-Weather Hackathon Risk:** Even when a live camera feed works cleanly, live traffic at presentation time may be completely dry — making it impossible to demonstrate flood detection and dynamic rerouting if the system only accepts live municipal cameras.

---

## 2. Compliant Multi-Adapter Ingestion Architecture

**Rule:** Never attempt authentication bypass, CAPTCHA solving, or aggressive scraping against public portals. Instead, implement `camera_extractor.py` behind a clean **FrameSource Adapter** interface where **every** source feeds real raw image bytes into `analyze_flood_image()` (Gemini 3.8 Flash Vision):

| Adapter Mode | Input Source | Use Case |
| :--- | :--- | :--- |
| `http_snapshot` | Authorized/configured HTTP JPEG snapshot endpoint (or local HTTP camera simulator) fetched server-side via `httpx` | Live camera polling when direct snapshot endpoints are available |
| `video_stream_or_clip` | Local `.mp4` / `.m3u8` / frame sequence of **real recorded flooding** at target intersections (e.g., Nguyen Huu Canh, Quoc Huong, Nguyen Trai) sampled via OpenCV (`cv2.VideoCapture`) | Deterministic, real-footage stage demo when live weather is dry or portal feeds are down |
| `local_image` | Curated real street flood test images in local storage | Unit/integration verification and single-frame testing |
| `crowdsourcing_upload` | Multipart/base64 image + GPS uploaded by driver/citizen via `POST /api/reports` | Live interactive audience/judge demo from any smartphone |

### OpenCV Video / Stream Sampling Pattern (Backend Worker)

```python
def sample_frame_from_stream(stream_or_video_path: str, frame_index: int = 0) -> bytes | None:
    """
    Extract a single JPEG frame from an HLS/RTSP URL or real flood MP4 file.
    Requires opencv-python-headless when video extraction is enabled.
    """
    import cv2

    cap = cv2.VideoCapture(stream_or_video_path)
    if not cap.isOpened():
        return None
    try:
        if frame_index > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        # Resize to max width 1024px to minimize Gemini Vision upload latency
        h, w = frame.shape[:2]
        if w > 1024:
            scale = 1024.0 / w
            frame = cv2.resize(frame, (1024, int(h * scale)))
        ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return bytes(buf) if ok_enc else None
    finally:
        cap.release()
```

---

## 3. Frame Deduplication & Rate Limiting

To stay comfortably inside Gemini API RPM/TPM limits while polling multiple cameras:
1. **Hash / Pixel Delta Filter:** Compute mean absolute grayscale difference (`Pillow` `ImageChops.difference` or small `32x32` grayscale numpy/byte comparison) against the last analyzed frame for that `camera_id`. Skip Gemini inference if the frame is static/identical.
2. **State Cooldown & TTL:** Once a camera reports `severity_level >= 2`, write `ttl_expires_at = now + 15 minutes` on Firestore and re-verify every `30–60s` rather than on every frame.

---

## 4. Reproducible Verification

```bash
# Test image preprocessing & camera snapshot ingestion (local synthetic JPEG + optional URL)
python scripts/repro_camera_fetch.py
```
