"""
core/face_cropper.py  —  Detection, alignement et recadrage de visage
Utilise InsightFace / RetinaFace (deja installe via buffalo_l)

Workflow :
  1. detect_faces()     -> liste de tous les visages detectes + thumbnails base64
  2. crop_and_align()   -> recadrage + alignement 5-points du visage selectionne
  3. Image alignee uploadee sur Yandex/Lens (pas la photo originale)
"""

import io
import cv2
import numpy as np
import base64
from pathlib import Path
from typing import Union, Optional


# Taille de sortie pour Yandex upload (assez grand pour la recherche visuelle)
OUTPUT_SIZE = 256
# Padding autour du visage (% de la taille du bbox)
FACE_PADDING = 0.35


def _load_img(image: Union[str, bytes, io.BytesIO]) -> Optional[np.ndarray]:
    """Charge une image en BGR numpy array."""
    if isinstance(image, (str, Path)):
        return cv2.imread(str(image))
    raw = image.read() if hasattr(image, "read") else image
    arr = np.frombuffer(raw, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _img_to_b64(img: np.ndarray, size: int = 96) -> str:
    """Redimensionne et encode en base64 JPEG pour le dashboard."""
    h, w = img.shape[:2]
    scale = size / max(h, w)
    resized = cv2.resize(img, (int(w*scale), int(h*scale)))
    _, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def detect_faces(image: Union[str, bytes, io.BytesIO], app) -> list:
    """
    Detecte tous les visages dans l'image.
    Retourne une liste de dicts :
      [
        {
          "index": 0,
          "bbox":  [x1, y1, x2, y2],
          "score": 0.99,
          "kps":   [[x,y], ...],  # 5 keypoints
          "thumb": "data:image/jpeg;base64,..."
        },
        ...
      ]
    """
    img = _load_img(image)
    if img is None:
        return []

    faces = app.get(img)
    if not faces:
        return []

    # Trier par taille (plus grand visage en premier)
    faces.sort(
        key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]),
        reverse=True
    )

    result = []
    h, w = img.shape[:2]
    for i, face in enumerate(faces):
        x1, y1, x2, y2 = [int(v) for v in face.bbox]
        # Padding
        pw = int((x2-x1) * FACE_PADDING)
        ph = int((y2-y1) * FACE_PADDING)
        cx1 = max(0, x1-pw)
        cy1 = max(0, y1-ph)
        cx2 = min(w, x2+pw)
        cy2 = min(h, y2+ph)
        crop = img[cy1:cy2, cx1:cx2]
        thumb = _img_to_b64(crop, size=96) if crop.size > 0 else ""
        result.append({
            "index": i,
            "bbox":  [x1, y1, x2, y2],
            "score": float(getattr(face, "det_score", 1.0)),
            "kps":   face.kps.tolist() if face.kps is not None else [],
            "thumb": thumb,
        })
    return result


def crop_and_align(
    image: Union[str, bytes, io.BytesIO],
    face_data: dict,
    output_size: int = OUTPUT_SIZE,
) -> io.BytesIO:
    """
    Recadre et aligne le visage selectionne.

    Algorithme :
      1. Rotation : angle calcule depuis les 2 yeux -> yeux horizontaux
      2. Crop avec padding -> visage centre
      3. Resize -> output_size x output_size
      4. Export BytesIO JPEG
    """
    img = _load_img(image)
    if img is None:
        raise ValueError("Image illisible")

    kps  = face_data.get("kps", [])
    bbox = face_data["bbox"]
    x1, y1, x2, y2 = bbox
    h_img, w_img   = img.shape[:2]

    # ── Alignement par les yeux (5 keypoints InsightFace) ───────────────────
    # kps ordre : [left_eye, right_eye, nose, left_mouth, right_mouth]
    if len(kps) >= 2:
        left_eye  = np.array(kps[0], dtype=np.float32)
        right_eye = np.array(kps[1], dtype=np.float32)

        # Angle entre les yeux
        dx    = right_eye[0] - left_eye[0]
        dy    = right_eye[1] - left_eye[1]
        angle = np.degrees(np.arctan2(dy, dx))

        # Centre de rotation = milieu des deux yeux
        eye_center = ((left_eye + right_eye) / 2).astype(int)
        eye_center = (int(eye_center[0]), int(eye_center[1]))

        if abs(angle) > 1.0:  # rotation seulement si inclinaison > 1deg
            M   = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
            img = cv2.warpAffine(img, M, (w_img, h_img), flags=cv2.INTER_LINEAR)

            # Recalculer bbox apres rotation
            corners = np.array([
                [x1, y1, 1], [x2, y1, 1], [x2, y2, 1], [x1, y2, 1]
            ], dtype=np.float32)
            rotated = (M @ corners.T).T
            x1 = int(rotated[:, 0].min())
            y1 = int(rotated[:, 1].min())
            x2 = int(rotated[:, 0].max())
            y2 = int(rotated[:, 1].max())

    # ── Crop avec padding ────────────────────────────────────────────────────
    pw = int((x2-x1) * FACE_PADDING)
    ph = int((y2-y1) * FACE_PADDING)
    cx1 = max(0, x1-pw)
    cy1 = max(0, y1-ph)
    cx2 = min(w_img, x2+pw)
    cy2 = min(h_img, y2+ph)
    crop = img[cy1:cy2, cx1:cx2]

    if crop.size == 0:
        crop = img  # fallback : image entiere

    # ── Resize carre ─────────────────────────────────────────────────────────
    # Carre avec bandes noires si ratio non carre
    h_c, w_c = crop.shape[:2]
    side      = max(h_c, w_c)
    square    = np.zeros((side, side, 3), dtype=np.uint8)
    y_off     = (side - h_c) // 2
    x_off     = (side - w_c) // 2
    square[y_off:y_off+h_c, x_off:x_off+w_c] = crop
    final     = cv2.resize(square, (output_size, output_size), interpolation=cv2.INTER_CUBIC)

    # ── Export ───────────────────────────────────────────────────────────────
    _, buf = cv2.imencode(".jpg", final, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return io.BytesIO(buf.tobytes())


def auto_crop(
    image: Union[str, bytes, io.BytesIO],
    app,
    output_size: int = OUTPUT_SIZE,
) -> tuple:
    """
    Detecte + recadre automatiquement le plus grand visage.
    Retourne (cropped_bytesio, faces_list, face_index_used).
    Si aucun visage : retourne (original_bytesio, [], None).
    """
    # Sauvegarder les bytes pour reutilisation
    if not isinstance(image, (str, Path)):
        raw   = image.read() if hasattr(image, "read") else image
        image = io.BytesIO(raw)
    else:
        raw = None

    faces = detect_faces(image, app)

    if not faces:
        if raw:
            return io.BytesIO(raw), [], None
        with open(str(image), "rb") as f:
            return io.BytesIO(f.read()), [], None

    # Recadrer le visage #0 (plus grand)
    if raw:
        image = io.BytesIO(raw)
    cropped = crop_and_align(image, faces[0], output_size)
    return cropped, faces, 0
