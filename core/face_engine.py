"""
core/face_engine.py  —  InsightFace ArcFace wrapper
Fix critique : tout appel InsightFace (C++ sync) tourne dans run_in_executor
pour ne JAMAIS bloquer l'event loop asyncio.
"""

import io, asyncio, numpy as np
from pathlib import Path
from typing import Optional, Union
from functools import partial

# ── Singleton ──────────────────────────────────────────────────────────────────
_ENGINE_CACHE: dict = {}

def get_engine(model_name: str = "buffalo_l") -> "FaceEngine":
    if model_name not in _ENGINE_CACHE:
        _ENGINE_CACHE[model_name] = FaceEngine(model_name)
    return _ENGINE_CACHE[model_name]


class FaceEngine:
    def __init__(self, model_name: str = "buffalo_l"):
        self.model_name = model_name
        self.app        = None
        self._load_model()


    def _ensure_model_exists(self):
        import os, urllib.request, zipfile
        from pathlib import Path
        try:
            from cli.interface import print_status
        except ImportError:
            print_status = lambda msg, status="info": print(msg)

        # InsightFace default model directory
        model_dir = Path.home() / ".insightface" / "models" / self.model_name

        # Check if directory exists and actually contains the detection model
        if not model_dir.exists() or not list(model_dir.glob("det_*.onnx")):
            print_status(f"[SYSTEM] Modèle '{self.model_name}' introuvable ou corrompu. Installation auto...", "warning")
            model_dir.parent.mkdir(parents=True, exist_ok=True)

            # Official GitHub release URL
            url = f"https://github.com/deepinsight/insightface/releases/download/v0.7/{self.model_name}.zip"
            zip_path = model_dir.parent / f"{self.model_name}.zip"

            try:
                print_status(f"[SYSTEM] Téléchargement depuis Github (approx. 330 Mo)... Patientez.")
                urllib.request.urlretrieve(url, zip_path)
                print_status("[SYSTEM] Téléchargement terminé. Extraction des modèles ONNX...")

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Extraction in the models directory
                    zip_ref.extractall(model_dir.parent)

                zip_path.unlink()  # Clean up the zip file
                print_status("[SYSTEM] Installation des modèles biométriques réussie !", "success")
            except Exception as e:
                print_status(f"[CRASH] Échec du téléchargement du modèle : {e}", "error")
                raise e

    def _load_model(self):
        # 1. On force la vérification et le téléchargement des modèles avant de charger InsightFace
        self._ensure_model_exists()

        try:
            from insightface.app import FaceAnalysis

            from cli.interface import print_status
            print_status(f"Loading InsightFace model: {self.model_name}...")
            self.app = FaceAnalysis(name=self.model_name, providers=["CPUExecutionProvider"])
            self.app.prepare(ctx_id=0, det_size=(640, 640))
            print_status(f"Model {self.model_name} ready.", "success")

            # --- PRO FEATURE: AdaFace Loading ---
            self.adaface = None
            try:
                import onnxruntime
                from pathlib import Path
                adaface_path = Path.home() / ".insightface" / "models" / "adaface_ir101.onnx"
                if adaface_path.exists():
                    self.adaface = onnxruntime.InferenceSession(str(adaface_path), providers=["CPUExecutionProvider"])
                    print_status("[PRO] AdaFace ONNX fusion module loaded.", "success")
                else:
                    print_status("[PRO] AdaFace ONNX introuvable (fusion désactivée).", "warning")
            except Exception as e:
                pass
        except ImportError:
            print("InsightFace non installé.")
            self.app = None

    # ── CPU-bound ops (sync) ───────────────────────────────────────────────────
    def _image_to_array(self, image):
        import cv2
        if isinstance(image, (str, Path)):
            return cv2.imread(str(image))
        raw = image.read() if hasattr(image, "read") else image
        arr = np.frombuffer(raw, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def get_embedding_sync(self, image, preprocess: bool = True) -> Optional[np.ndarray]:
        """
        Synchrone — NE PAS appeler directement dans une coroutine.
        preprocess=True : applique CLAHE + denoising + sharpening avant detection.
        """
        if self.app is None:
            return None
        # Pretraitement image (ameliore la precision ArcFace sur images floues/sombres)
        if preprocess:
            try:
                from core.preprocessor import preprocess as pp
                image = pp(image)
            except Exception:
                pass  # si preprocess echoue, on continue avec l'original
        img_arr = self._image_to_array(image)
        if img_arr is None:
            return None
        faces = self.app.get(img_arr)
        if not faces:
            return None
        face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
        
        self.last_keypoints = face.kps.tolist() if hasattr(face, 'kps') and face.kps is not None else []
        return face.embedding

    # Alias legacy
    def get_embedding(self, image) -> Optional[np.ndarray]:
        return self.get_embedding_sync(image)

    # ── Async wrappers (run_in_executor) ───────────────────────────────────────
    async def get_embedding_async(self, image) -> Optional[np.ndarray]:
        """Version async : tourne InsightFace dans un thread → event loop libre."""
        loop = asyncio.get_event_loop()
        # Lire les bytes avant d'aller dans le thread (BytesIO non thread-safe)
        if hasattr(image, "read"):
            raw = image.read()
            image = io.BytesIO(raw)
        return await loop.run_in_executor(None, self.get_embedding_sync, image)

    def arcface_distance(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        e1 = emb1 / np.linalg.norm(emb1)
        e2 = emb2 / np.linalg.norm(emb2)
        return float(np.clip((1 - np.dot(e1, e2)) / 2, 0, 1))

    # ── Fetch + embed (async, non-bloquant) ────────────────────────────────────
    async def fetch_and_embed_async(
        self,
        url: str,
        thumb_url: Optional[str],
        stealth: bool = False
    ) -> Optional[np.ndarray]:
        """
        1. Télécharge l'image via httpx (await → non-bloquant)
        2. Lance InsightFace dans un thread (run_in_executor → non-bloquant)
        Timeout total : 10s par URL.
        """
        targets = [u for u in [thumb_url, url] if u and str(u).startswith("http")]
        if not targets:
            return None

        try:
            import httpx
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/123.0.0.0"
            }
            async with httpx.AsyncClient(
                timeout=10.0, follow_redirects=True, verify=False
            ) as client:
                for target_url in targets:
                    try:
                        resp = await client.get(target_url, headers=headers)
                        if resp.status_code == 200 and resp.content:
                            emb = await self.get_embedding_async(io.BytesIO(resp.content))
                            if emb is not None:
                                return emb
                    except Exception:
                        continue

        except ImportError:
            # httpx absent → urllib dans executor
            loop = asyncio.get_event_loop()
            for target_url in targets:
                try:
                    emb = await loop.run_in_executor(
                        None, self._fetch_embed_sync, target_url
                    )
                    if emb is not None:
                        return emb
                except Exception:
                    continue

        return None

    def _fetch_embed_sync(self, url: str) -> Optional[np.ndarray]:
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
            return self.get_embedding_sync(io.BytesIO(data))
        except Exception:
            return None

    def load_image_bytes(self, path: str, stealth: bool):
        if not stealth:
            return path
        with open(path, "rb") as f:
            return io.BytesIO(f.read())

    def process_single(self, image_path, scraper, threshold, stealth):
        from cli.interface import print_status, print_match, console
        print_status("Extraction embeddings...")
        src        = self.load_image_bytes(image_path, stealth)
        target_emb = self.get_embedding_sync(src)
        if target_emb is None:
            print_status("Aucun visage détecté.", "error")
            return []
        print_status("Visage détecté — pivot Yandex...", "success")
        raw = scraper.search_image_sync(self.load_image_bytes(image_path, stealth))
        confirmed = []

        async def _run():
            for i, result in enumerate(raw, 1):
                print_status(f"insightFace Analyzing Link {i}/{len(raw)} ({result['platform']})")
                try:
                    cand = await self.fetch_and_embed_async(
                        result["url"], result.get("thumb"), stealth
                    )
                    if cand is not None:
                        dist = self.arcface_distance(target_emb, cand)
                        if dist < threshold:
                            confirmed.append({**result, "distance": dist, "confidence": (1-dist)*100})
                            print_match(image_path, result["url"], result["platform"], dist)
                except Exception as e:
                    print_status(f"Erreur lien {i}: {e}", "error")
            return confirmed

        return asyncio.run(_run())

    def process_directory(self, dir_path, scraper, threshold, stealth, output_dir):
        import json
        from cli.interface import print_status
        images = [
            str(p) for p in Path(dir_path).rglob("*")
            if p.suffix.lower() in {".jpg",".jpeg",".png",".webp",".bmp"}
        ]
        print_status(f"{len(images)} images trouvées dans {dir_path}")
        all_results = {}
        for img_path in images:
            print_status(f"Traitement : {Path(img_path).name}")
            all_results[img_path] = self.process_single(img_path, scraper, threshold, stealth)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        out = Path(output_dir) / "shadow_match_results.json"
        with open(out, "w") as f:
            json.dump(all_results, f, indent=2)
        print_status(f"Résultats → {out}", "success")

    def print_results(self, results):
        from cli.interface import console
        from rich.table import Table
        from rich import box
        if not results:
            print("Aucun match confirmé.")
            return
        table = Table(title="CONFIRMED MATCHES", box=box.ROUNDED, border_style="bright_blue")
        table.add_column("PLATFORM", style="bright_cyan")
        table.add_column("ARCFACE %", style="bold magenta")
        table.add_column("URL", style="bright_blue", max_width=60)
        for r in sorted(results, key=lambda x: x["distance"]):
            table.add_row(r["platform"].upper(), f"{r['confidence']:.1f}%", r["url"])
        console.print(table)
