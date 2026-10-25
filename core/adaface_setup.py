"""
core/adaface_setup.py  —  Détection / téléchargement / configuration du modèle AdaFace ONNX

Corrige l'avertissement :
    [PRO] AdaFace ONNX introuvable (fusion désactivée).

Ce que fait ce module (même logique que core/playwright_setup.py) :
  1. Cherche le modèle : chemin forcé (env / config) -> ~/.insightface/models/adaface_ir101.onnx
     -> noms alternatifs (adaface_ir_101.onnx, ...) -> ./models/ du projet.
  2. Valide le fichier (chargement ONNX Runtime : entrée 3x112x112, sortie 512D).
     Un fichier tronqué / corrompu est mis de côté (.invalid) puis re-téléchargé.
  3. S'il est absent : téléchargement (~249 Mo) avec reprise, contrôle de taille et SHA-256,
     fichier .part promu atomiquement seulement s'il est intact. Deux sources :
       - GitHub  : yakhyo/adaface-onnx (release "weights"), licence MIT
       - Hugging Face : yakhyo/uniface-weights (commit épinglé)
     Les deux fournissent exactement le même fichier (même SHA-256).
  4. Écrit le résultat dans `shadow_match.config.json` (clé "adaface").

Modèle : AdaFace IR-101 entraîné sur WebFace12M (Kim et al., CVPR 2022), export ONNX tiers.
Il n'est PAS inclus dans le dépôt ; vérifie sa licence / ses conditions d'usage selon ton cas.

Variables d'environnement :
  SHADOWMATCH_ADAFACE=0        désactive totalement AdaFace (ni détection ni téléchargement)
  SHADOWMATCH_ADAFACE_PATH     chemin forcé vers un .onnx AdaFace
  SHADOWMATCH_AUTO_INSTALL=0   n'autorise aucun téléchargement automatique (partagé avec Playwright)

CLI :  python -m core.adaface_setup [--check] [--force] [--path FILE] [--no-download]
       python main.py --setup            (inclut AdaFace, sauf --skip-adaface)
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core.playwright_setup import (
    PROJECT_ROOT,
    _auto_install_enabled,
    config_path,
    load_config,
    save_config,
)

# ── Modèle de référence ───────────────────────────────────────────────────────────
ADAFACE_FILENAME = "adaface_ir101.onnx"   # nom attendu par core/face_engine.py
ADAFACE_SIZE = 260_704_652
ADAFACE_SHA256 = "f2eb07d03de0af560a82e1214df799fec5e09375d43521e2868f9dc387e5a43e"
ADAFACE_SOURCES = (
    ("GitHub (yakhyo/adaface-onnx)",
     "https://github.com/yakhyo/adaface-onnx/releases/download/weights/adaface_ir_101.onnx"),
    ("Hugging Face (yakhyo/uniface-weights)",
     "https://huggingface.co/yakhyo/uniface-weights/resolve/"
     "13f64660d271d74aa7cc2e86c43d39da551848a5/adaface_ir_101.onnx"),
)
ALT_FILENAMES = (
    ADAFACE_FILENAME,
    "adaface_ir_101.onnx",
    "adaface_ir101_webface12m.onnx",
    "adaface_ir101web12m.onnx",
)
MIN_PLAUSIBLE_SIZE = 5 * 1024 * 1024       # en dessous : fichier clairement tronqué / HTML d'erreur
USER_AGENT = "ShadowMatch/2.x (+https://github.com/data2391/shadow-matchv1)"

LogFn = Callable[[str], None]


# ══════════════════════════════════════════════════════════════════════════════
#  Emplacements
# ══════════════════════════════════════════════════════════════════════════════
def models_dir() -> Path:
    """Même dossier que core/face_engine.py (modèles InsightFace)."""
    return Path.home() / ".insightface" / "models"


def default_model_path() -> Path:
    return models_dir() / ADAFACE_FILENAME


def adaface_enabled(cfg: Optional[dict] = None) -> bool:
    env = os.environ.get("SHADOWMATCH_ADAFACE")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off")
    return bool(((cfg if cfg is not None else load_config()).get("adaface") or {}).get("enabled", True))


def _candidates(cfg: dict) -> list:
    """Liste ordonnée de (chemin, origine)."""
    out = []
    forced = os.environ.get("SHADOWMATCH_ADAFACE_PATH") or (cfg.get("adaface") or {}).get("path_override")
    if forced:
        out.append((Path(forced).expanduser(), "override"))
    for d in (models_dir(), models_dir() / "adaface", PROJECT_ROOT / "models"):
        for n in ALT_FILENAMES:
            out.append((d / n, "found"))
    return out


def find_adaface(cfg: Optional[dict] = None, log: LogFn = print) -> tuple:
    """-> (Path | None, origine | None). Ne valide pas le contenu."""
    cfg = cfg if cfg is not None else load_config()
    seen = set()
    for p, origin in _candidates(cfg):
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p, origin
        if origin == "override":
            log(f"⚠ Chemin AdaFace forcé introuvable : {p} — détection automatique.")
    return None, None


# ══════════════════════════════════════════════════════════════════════════════
#  Validation
# ══════════════════════════════════════════════════════════════════════════════
def validate_model(path: Path) -> tuple:
    """
    -> (ok, détail). Charge le .onnx avec ONNX Runtime et contrôle les formes :
    entrée (N, 3, 112, 112), sortie (N, 512). Sans onnxruntime : contrôle de taille seulement.
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        return False, str(e)
    if size < MIN_PLAUSIBLE_SIZE:
        return False, f"fichier trop petit ({size} octets) — tronqué ou corrompu"
    try:
        import onnxruntime as ort
    except ImportError:
        return True, "onnxruntime absent : seule la taille a été contrôlée"
    try:
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        ishape = sess.get_inputs()[0].shape
        oshape = sess.get_outputs()[0].shape
    except Exception as e:                          # protobuf invalide, fichier tronqué...
        return False, f"ONNX illisible : {str(e).splitlines()[0][:160]}"
    if len(ishape) != 4 or list(ishape[1:]) != [3, 112, 112]:
        return False, f"entrée inattendue {ishape} (attendu [N, 3, 112, 112])"
    if not oshape or oshape[-1] != 512:
        return False, f"sortie inattendue {oshape} (attendu [N, 512])"
    return True, f"entrée {ishape} -> sortie {oshape}"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
#  Téléchargement (reprise + SHA-256 + écriture atomique)
# ══════════════════════════════════════════════════════════════════════════════
def _fmt_mb(n: int) -> str:
    return f"{n / 1_048_576:.0f} Mo"


def _stream_to_part(url: str, part: Path, expected_size: int, log: LogFn, timeout: int = 30) -> bool:
    """Télécharge `url` vers `part` en reprenant s'il existe déjà un morceau. True si complet."""
    have = part.stat().st_size if part.exists() else 0
    if have > expected_size:                       # morceau incohérent
        part.unlink()
        have = 0

    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
        log(f"  ↻ Reprise à {_fmt_mb(have)} / {_fmt_mb(expected_size)}")
    req = urllib.request.Request(url, headers=headers)

    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 416:                          # Range hors limites : on repart de zéro
            part.unlink(missing_ok=True)
            return False
        raise

    with resp:
        status = getattr(resp, "status", 200)
        mode = "ab"
        if have and status != 206:                 # le serveur ignore Range -> on réécrit tout
            mode, have = "wb", 0
        clen = int(resp.headers.get("Content-Length") or 0)
        total = (have + clen) if clen else expected_size

        done, last_pct, last_t = have, -1, time.time()
        with open(part, mode) as out:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else 0
                if pct // 10 > last_pct // 10 or time.time() - last_t > 15:
                    log(f"  ⬇ {pct:3d}%  ({_fmt_mb(done)} / {_fmt_mb(total)})")
                    last_pct, last_t = pct, time.time()
    return part.stat().st_size == expected_size


def download_adaface(
    dest: Optional[Path] = None,
    log: LogFn = print,
    sources=ADAFACE_SOURCES,
    expected_size: int = ADAFACE_SIZE,
    expected_sha256: str = ADAFACE_SHA256,
    attempts_per_source: int = 3,
) -> bool:
    """Télécharge AdaFace IR-101 vers `dest`. N'écrit `dest` que si le fichier est intact."""
    dest = dest or default_model_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    free = shutil.disk_usage(dest.parent).free
    part = dest.with_name(dest.name + ".part")
    needed = expected_size - (part.stat().st_size if part.exists() else 0)
    if free < needed * 1.1:
        log(f"✖ Espace disque insuffisant dans {dest.parent} : {_fmt_mb(free)} libres, "
            f"{_fmt_mb(needed)} nécessaires.")
        return False

    log(f"⬇ Téléchargement d'AdaFace IR-101 ({_fmt_mb(expected_size)}) -> {dest}")
    for label, url in sources:
        log(f"  Source : {label}")
        for attempt in range(1, attempts_per_source + 1):
            try:
                complete = _stream_to_part(url, part, expected_size, log)
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403, 404, 410):
                    log(f"  ✖ HTTP {e.code} — source indisponible, passage à la suivante.")
                    break                            # inutile de réessayer cette source
                reason = getattr(e, "reason", e)
                log(f"  ⚠ Interruption ({reason}) — tentative {attempt}/{attempts_per_source}")
                time.sleep(min(2 * attempt, 6))
                continue
            if not complete:
                log(f"  ⚠ Fichier incomplet — tentative {attempt}/{attempts_per_source}")
                continue

            log("  Vérification SHA-256...")
            digest = sha256_file(part)
            if digest != expected_sha256:
                log(f"  ✖ SHA-256 invalide ({digest[:16]}... au lieu de {expected_sha256[:16]}...) "
                    "— fichier rejeté.")
                part.unlink(missing_ok=True)
                break                                # source suivante
            os.replace(part, dest)                   # promotion atomique
            log(f"✔ AdaFace téléchargé et vérifié : {dest}")
            return True
    log("✖ Téléchargement impossible depuis toutes les sources.")
    log(f"  Manuel : curl -L -o '{dest}' '{sources[0][1]}'")
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  API principale
# ══════════════════════════════════════════════════════════════════════════════
def ensure_adaface(
    log: LogFn = print,
    auto_download: Optional[bool] = None,
    force: bool = False,
) -> dict:
    """
    Détecte, télécharge si besoin, valide, écrit la config. Retourne :
      {"ok": bool, "path": str|None, "source": "override"|"found"|"downloaded"|None,
       "enabled": bool, "detail": str}
    Appel quasi instantané quand le fichier est déjà validé (cache dans la config).
    """
    cfg = load_config()
    if not adaface_enabled(cfg):
        return {"ok": False, "path": None, "source": None, "enabled": False,
                "detail": "désactivé (SHADOWMATCH_ADAFACE=0 / config)"}
    if auto_download is None:
        auto_download = _auto_install_enabled(cfg)

    info = {"ok": False, "path": None, "source": None, "enabled": True, "detail": ""}
    path, origin = find_adaface(cfg, log)

    # ── Cache : fichier inchangé depuis la dernière validation réussie ──────────
    cached = cfg.get("adaface") or {}
    if path and not force and cached.get("ok") and cached.get("path") == str(path):
        st = path.stat()
        if cached.get("size") == st.st_size and cached.get("mtime_ns") == st.st_mtime_ns:
            return {**info, "ok": True, "path": str(path), "source": origin,
                    "detail": cached.get("detail", "")}

    # ── Validation du fichier trouvé ────────────────────────────────────────────
    if path:
        ok, detail = validate_model(path)
        if ok:
            log(f"✔ AdaFace détecté : {path}")
            return _save_ok(cfg, info, path, origin or "found", detail)
        log(f"⚠ AdaFace invalide ({path}) : {detail}")
        if origin == "override":
            log("  Le chemin forcé n'est pas utilisable — repli sur le téléchargement automatique.")
        else:
            bad = path.with_name(path.name + ".invalid")
            try:
                os.replace(path, bad)
                log(f"  Fichier mis de côté : {bad.name}")
            except OSError:
                pass
        path = None

    # ── Téléchargement ──────────────────────────────────────────────────────────
    if not path:
        log(f"⚠ AdaFace ONNX introuvable ({default_model_path()})")
        if not auto_download:
            log("  Auto-download désactivé -> lance : python -m core.adaface_setup")
            info["detail"] = "absent, téléchargement automatique désactivé"
            return _save_fail(cfg, info)
        dest = default_model_path()
        if download_adaface(dest, log):
            ok, detail = validate_model(dest)
            if ok:
                return _save_ok(cfg, info, dest, "downloaded", detail)
            log(f"✖ Le fichier téléchargé ne passe pas la validation : {detail}")
            info["detail"] = detail
        else:
            info["detail"] = "téléchargement impossible"
    return _save_fail(cfg, info)


def _save_ok(cfg: dict, info: dict, path: Path, source: str, detail: str) -> dict:
    st = path.stat()
    cfg_ad = cfg.get("adaface") or {}
    cfg["adaface"] = {
        "enabled": cfg_ad.get("enabled", True),
        "path_override": cfg_ad.get("path_override"),
        "ok": True,
        "path": str(path),
        "source": source,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "detail": detail,
        "model": "AdaFace IR-101 (WebFace12M)",
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_config(cfg)
    return {**info, "ok": True, "path": str(path), "source": source, "detail": detail}


def _save_fail(cfg: dict, info: dict) -> dict:
    cfg_ad = cfg.get("adaface") or {}
    cfg["adaface"] = {
        "enabled": cfg_ad.get("enabled", True),
        "path_override": cfg_ad.get("path_override"),
        "ok": False,
        "path": None,
        "detail": info.get("detail", ""),
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_config(cfg)
    return info


def load_adaface_session(log: LogFn = print, **kwargs):
    """
    Utilisé par FaceEngine : garantit le fichier puis retourne une onnxruntime.InferenceSession
    (CPU), ou None si AdaFace est indisponible (l'outil continue sans fusion).
    """
    info = ensure_adaface(log, **kwargs)
    if not info["ok"]:
        return None
    try:
        import onnxruntime
        return onnxruntime.InferenceSession(info["path"], providers=["CPUExecutionProvider"])
    except Exception as e:
        log(f"⚠ AdaFace : chargement impossible ({str(e).splitlines()[0][:160]})")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Diagnostic / CLI
# ══════════════════════════════════════════════════════════════════════════════
def diagnostic_lines() -> list:
    cfg = load_config()
    ad = cfg.get("adaface") or {}
    path, origin = find_adaface(cfg, lambda m: None)
    return [
        f"AdaFace activé    : {adaface_enabled(cfg)}",
        f"Dossier modèles   : {models_dir()}",
        f"Fichier trouvé    : {path or '-'}" + (f"  ({_fmt_mb(path.stat().st_size)})" if path else ""),
        f"Validé (config)   : {ad.get('ok', '-')}  {ad.get('detail', '')}".rstrip(),
        f"Override          : {ad.get('path_override') or os.environ.get('SHADOWMATCH_ADAFACE_PATH') or '-'}",
    ]


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="SHADOW-MATCH — setup AdaFace ONNX")
    ap.add_argument("--check", action="store_true", help="diagnostic seulement, rien n'est téléchargé")
    ap.add_argument("--force", action="store_true", help="ignore le cache et re-valide")
    ap.add_argument("--no-download", action="store_true", help="détecte sans télécharger")
    ap.add_argument("--path", metavar="FILE", help="utiliser ce .onnx AdaFace (enregistré dans la config)")
    a = ap.parse_args(argv)

    if a.path:
        p = Path(a.path).expanduser()
        if not p.is_file():
            print(f"✖ Fichier introuvable : {p}")
            return 1
        cfg = load_config()
        cfg.setdefault("adaface", {})["path_override"] = str(p.resolve())
        save_config(cfg)
        print(f"✔ Chemin AdaFace enregistré dans {config_path()}")

    if a.check:
        print("\n".join(diagnostic_lines()))
        return 0
    info = ensure_adaface(print, auto_download=False if a.no_download else None, force=a.force)
    print("\n" + "\n".join(diagnostic_lines()))
    if not info["enabled"]:
        print("\n=> DÉSACTIVÉ")
        return 0
    print(f"\n=> {'OK' if info['ok'] else 'ECHEC'} ({info['source'] or info['detail']})")
    return 0 if info["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
