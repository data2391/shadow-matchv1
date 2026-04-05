"""
core/preprocessor.py  —  Pipeline de prétraitement image avant InsightFace
Etapes : CLAHE -> Denoising -> Sharpening -> export BytesIO
"""

import io
import cv2
import numpy as np
from pathlib import Path
from typing import Union


def preprocess(image: Union[str, bytes, io.BytesIO], log_fn=None) -> io.BytesIO:
    """
    Applique CLAHE + denoising + sharpening sur une image.
    Retourne un BytesIO JPEG pret pour InsightFace / Yandex upload.
    log_fn : callable optionnel pour logguer les etapes (ex: print ou broadcast)
    """

    def _log(msg):
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass
        else:
            print(msg)

    # ── Lecture ──────────────────────────────────────────────────────────────
    if isinstance(image, (str, Path)):
        img = cv2.imread(str(image))
    else:
        raw = image.read() if hasattr(image, "read") else image
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        _log("  [PREPROC] Image illisible — image originale conservee")
        if isinstance(image, io.BytesIO):
            image.seek(0)
            return image
        with open(str(image), "rb") as f:
            return io.BytesIO(f.read())

    original_shape = img.shape
    _log(f"  [PREPROC] Image {original_shape[1]}x{original_shape[0]}px — pipeline demarre")

    # ── 1. Upscale si trop petite (< 200px) ──────────────────────────────────
    h, w = img.shape[:2]
    if min(h, w) < 200:
        scale = 200 / min(h, w)
        img   = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        _log(f"  [PREPROC] Upscale x{scale:.1f} -> {img.shape[1]}x{img.shape[0]}px")

    # ── 2. CLAHE — amelioration contraste local ───────────────────────────────
    # Travaille sur le canal L (luminance) en espace LAB
    lab   = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_eq  = clahe.apply(l)
    img   = cv2.cvtColor(cv2.merge([l_eq, a, b]), cv2.COLOR_LAB2BGR)
    _log("  [PREPROC] CLAHE applique (contraste local)")

    # ── 3. Denoising — vire le grain (photos de nuit / compressees) ──────────
    # h=7 : leger, preserve les details du visage
    img = cv2.fastNlMeansDenoisingColored(img, None, h=7, hColor=7,
                                          templateWindowSize=7, searchWindowSize=21)
    _log("  [PREPROC] Denoising applique (grain retire)")

    # ── 4. Sharpening — durcit contours yeux / bouche (cles ArcFace) ─────────
    # Unsharp masking : original + alpha * (original - blur)
    blur    = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
    img     = cv2.addWeighted(img, 1.5, blur, -0.5, 0)
    img     = np.clip(img, 0, 255).astype(np.uint8)
    _log("  [PREPROC] Sharpening applique (contours renforces)")

    # ── Export BytesIO JPEG qualite 95 ────────────────────────────────────────
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        _log("  [PREPROC] Encodage JPEG echoue — image originale conservee")
        if isinstance(image, io.BytesIO):
            image.seek(0)
            return image
        with open(str(image), "rb") as f:
            return io.BytesIO(f.read())

    _log("  [PREPROC] Pipeline termine — image optimisee pour ArcFace")
    return io.BytesIO(buf.tobytes())
