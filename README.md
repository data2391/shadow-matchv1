# SHADOW-MATCH v2.0
> OSINT Facial Recognition Engine

## Quick Start

```bash
# Install
pip install -r requirements.txt
playwright install chromium

# CLI — single image
python main.py --image target.jpg

# CLI — batch folder (use buffalo_s to avoid CPU overload)
python main.py -d ./targets --model buffalo_s

# Stealth mode — zero disk traces
python main.py --image target.jpg -S

# Web Dashboard
python main.py --web
# → http://localhost:8080
```

## Architecture
```
shadow_match/
├── main.py                  ← Entry point + CLI args + splash screen
├── requirements.txt
├── core/
│   ├── face_engine.py       ← InsightFace ArcFace (buffalo_l / buffalo_s)
│   ├── yandex_scraper.py    ← Playwright + Captcha handler + BytesIO stealth
│   └── cleanup.py           ← Upload folder janitor (max 2h retention)
├── web/
│   ├── server.py            ← FastAPI + WebSocket live feed
│   └── templates/
│       └── dashboard.html   ← Cyber dashboard (drop-zone, live feed, gallery)
└── cli/
    └── interface.py         ← Rich ASCII splash + status printer
```

## Key Features
| Feature | Detail |
|---|---|
| **Captcha Handling** | Auto-detects Yandex captcha → notifies web UI or pauses CLI |
| **Stealth Mode (-S)** | BytesIO pipeline — zero images written to disk |
| **Auto-Cleanup** | Uploads older than 2h auto-deleted on startup |
| **Engine Switch** | `--model buffalo_l` (precise) / `buffalo_s` (fast batch) |
| **Live Feed** | Playwright → WebSocket → Dashboard in real-time |
| **ArcFace Threshold** | Default 0.35 — configurable via `--threshold` or web UI |
