"""
web/server.py  —  FastAPI + WebSocket — SHADOW-MATCH Dashboard
"""
import asyncio, io, json, time, uuid, traceback
from pathlib import Path
from typing import Set

BASE_DIR   = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "web" / "uploads"
STATIC_DIR = BASE_DIR / "web" / "static"
TMPL_DIR   = BASE_DIR / "web" / "templates"
for d in [UPLOAD_DIR, STATIC_DIR, TMPL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

app = FastAPI(title="SHADOW-MATCH", docs_url=None, redoc_url=None)
app.mount("/static",  StaticFiles(directory=str(STATIC_DIR),  html=False), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR),  html=False), name="uploads")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(f"[ERROR] {tb}")
    return JSONResponse(status_code=500, content={"error": str(exc), "traceback": tb})

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)
    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)
    async def broadcast(self, message: str):
        dead = set()
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self.active -= dead

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    tmpl_path = TMPL_DIR / "dashboard.html"
    if not tmpl_path.exists():
        return HTMLResponse("<h1 style='color:red'>dashboard.html introuvable</h1>", status_code=500)
    return HTMLResponse(content=tmpl_path.read_text(encoding="utf-8"))

@app.get("/debug", response_class=PlainTextResponse)
async def debug():
    lines = [
        "=== SHADOW-MATCH DEBUG ===",
        f"Python      : {__import__('sys').version}",
        f"BASE_DIR    : {BASE_DIR}",
        f"UPLOAD_DIR  : {UPLOAD_DIR}  exists={UPLOAD_DIR.exists()}",
        f"dashboard   : {(TMPL_DIR / 'dashboard.html').exists()}",
        "",
        "--- Packages ---",
    ]
    for pkg in ["fastapi","uvicorn","insightface","onnxruntime","playwright","cv2","numpy","rich","httpx"]:
        try:
            mod = __import__(pkg)
            lines.append(f"  {pkg:15}: OK   {getattr(mod, '__version__', '?')}")
        except ImportError:
            lines.append(f"  {pkg:15}: MISSING")
    return "\n".join(lines)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)

@app.post("/detect")
async def detect_faces_route(
    file:  UploadFile = File(...),
    model: str        = Form("buffalo_l"),
):
    """
    Detecte les visages dans l'image uploadee.
    Retourne les thumbnails base64 pour la selection dans le dashboard.
    """
    try:
        img_bytes = await file.read()
        from core.face_engine import get_engine
        from core.face_cropper import detect_faces
        engine = get_engine(model_name=model)
        faces  = detect_faces(io.BytesIO(img_bytes), engine.app)
        return JSONResponse({"faces": faces, "count": len(faces)})
    except Exception as e:
        return JSONResponse({"error": str(e), "faces": [], "count": 0}, status_code=500)


@app.post("/scan")
async def scan(
    file:       UploadFile = File(...),
    stealth:    bool       = Form(False),
    model:      str        = Form("buffalo_l"),
    threshold:  float      = Form(0.35),
    face_index: int        = Form(-1),   # -1 = auto (plus grand visage)
):
    try:
        img_bytes   = await file.read()
        preview_url = None
        if not stealth:
            fname     = f"{uuid.uuid4().hex[:12]}{Path(file.filename).suffix}"
            save_path = UPLOAD_DIR / fname
            save_path.write_bytes(img_bytes)
            preview_url = f"/uploads/{fname}"
            try:
                from core.cleanup import CleanupManager
                CleanupManager(str(UPLOAD_DIR), max_age_hours=2).run()
            except Exception:
                pass
        async def _broadcast(msg: str):
            await manager.broadcast(msg)
        asyncio.create_task(_run_scan(img_bytes, stealth, model, threshold, _broadcast, preview_url, face_index))
        return JSONResponse({"status": "started", "preview": preview_url})
    except Exception as e:
        return JSONResponse({"error": str(e), "traceback": traceback.format_exc()}, status_code=500)


async def _run_scan(img_bytes, stealth, model_name, threshold, broadcast, preview_url, face_index=-1):
    try:
        ts = lambda: time.strftime("%H:%M:%S")
        await broadcast(f"[{ts()}] Ghost_1 Account Pool Active...")

        from core.face_engine import get_engine
        from core.yandex_scraper import YandexScraper

        engine  = get_engine(model_name=model_name)
        scraper = YandexScraper(stealth=stealth, ws_broadcast=broadcast, headless=False)

        await broadcast(f"[{ts()}] Pretraitement image (CLAHE + Denoising + Sharpening)...")

        # ── Detection + alignement du visage ──────────────────────────────────
        from core.face_cropper import detect_faces, crop_and_align, auto_crop
        loop = asyncio.get_event_loop()

        def _detect_and_crop():
            from core.face_cropper import detect_faces, crop_and_align, auto_crop
            import io as _io
            faces = detect_faces(_io.BytesIO(img_bytes), engine.app)
            if not faces:
                return None, [], _io.BytesIO(img_bytes)
            idx = face_index if (0 <= face_index < len(faces)) else 0
            cropped = crop_and_align(_io.BytesIO(img_bytes), faces[idx])
            return idx, faces, cropped

        idx_used, faces, search_image = await loop.run_in_executor(None, _detect_and_crop)

        if faces:
            await broadcast(f"[{ts()}] {len(faces)} visage(s) detecte(s) — cible : visage #{idx_used}")
            await broadcast(f"[{ts()}] Recadrage + alignement 5-points (yeux, nez, bouche)...")
        else:
            await broadcast(f"[{ts()}] Aucun visage detecte — image originale utilisee")

        # ── Embedding sur le visage recadre ───────────────────────────────────
        await broadcast(f"[{ts()}] Extraction embedding ArcFace...")
        search_image.seek(0)
        target_emb = await engine.get_embedding_async(io.BytesIO(search_image.read()))
        if target_emb is None:
            await broadcast("__ERROR__ Aucun visage detecte dans l'image cible.")
            return
        await broadcast(f"[{ts()}] Embedding extrait — pivot multi-moteur (Yandex / Lens / Bing)...")

        # Utiliser le visage recadre pour la recherche visuelle (pas l'image brute)
        search_image.seek(0)
        raw = await scraper.search_image(io.BytesIO(search_image.read()))
        await broadcast(f"[{ts()}] {len(raw)} visual matches found — analyse ArcFace...")
        confirmed = []

        for i, result in enumerate(raw, 1):
            await broadcast(f"[{ts()}] insightFace Analyzing Link {i}/{len(raw)} ({result['platform']})...")
            try:
                cand_emb = await engine.fetch_and_embed_async(
                    result["url"], result.get("thumb"), stealth
                )
                if cand_emb is not None:
                    dist       = engine.arcface_distance(target_emb, cand_emb)
                    confidence = round((1 - dist) * 100, 1)
                    await broadcast(f"[{ts()}]   -> {confidence:.1f}% (dist={dist:.3f})")
                    if dist < threshold:
                        match_data = {
                            **result,
                            "distance":   round(dist, 4),
                            "confidence": confidence,
                            "preview":    preview_url,
                        }
                        confirmed.append(match_data)
                        await broadcast(f"[{ts()}] MATCH CONFIRMED {result['platform'].upper()} | {confidence}%")
                        await broadcast("__MATCH__" + json.dumps(match_data))
                else:
                    await broadcast(f"[{ts()}]   -> aucun visage detecte")
            except Exception as e:
                await broadcast(f"[{ts()}] Erreur lien {i}: {e}")
            await asyncio.sleep(0)

        await broadcast(f"[{ts()}] SCAN TERMINE — {len(confirmed)} match(s) confirme(s).")
        await broadcast("__DONE__" + json.dumps(confirmed))

    except Exception as e:
        tb = traceback.format_exc()
        print("[_run_scan ERROR]")
        print(tb)
        await broadcast("__ERROR__ " + str(e))


def run_server(host: str = "0.0.0.0", port: int = 8080):
    print(f"\n  SHADOW-MATCH  ->  http://localhost:{port}")
    print(f"  Debug         ->  http://localhost:{port}/debug\n")
    uvicorn.run("web.server:app", host=host, port=port, log_level="info", reload=False)
