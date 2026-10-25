"""
core/venv_bootstrap.py  —  Environnement virtuel (venv) pour SHADOW-MATCH

Stdlib uniquement : doit pouvoir tourner AVANT que rich / playwright / insightface
soient installés (c'est justement son rôle).

Ce que fait ce module :
  * find_venv()            : repère un venv du projet (.venv, venv, env) ou celui de la config
  * maybe_reexec_in_venv() : si un venv existe et qu'on n'est pas dedans, relance main.py
                             avec le Python du venv (os.execv sous POSIX, subprocess sous Windows)
  * setup()                : `python main.py --setup`
                               1) crée .venv si nécessaire (ou réutilise le venv actif)
                               2) pip install -r requirements.txt  (avec le pip DU venv)
                               3) installe Playwright + Chromium avec le Python DU venv
                               4) écrit le venv dans shadow_match.config.json

Pourquoi un venv : Kali / Debian / Ubuntu récents refusent `pip install` hors venv
("externally-managed-environment", PEP 668), et `playwright install` doit être lancé
avec le même Python que celui qui exécutera l'outil.

Variables d'environnement :
  SHADOWMATCH_VENV      dossier du venv à utiliser / créer
  SHADOWMATCH_NO_VENV   1 -> ne jamais relancer dans un venv (utilise le Python courant)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import venv as _venv
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VENV_NAMES = (".venv", "venv", "env")   # ordre de détection
DEFAULT_CREATE_NAME = ".venv"
REEXEC_FLAG = "SHADOWMATCH_VENV_ACTIVE"

LogFn = Callable[[str], None]


# ══════════════════════════════════════════════════════════════════════════════
#  Détection
# ══════════════════════════════════════════════════════════════════════════════
def in_venv() -> bool:
    """True si l'interpréteur courant tourne dans un venv (ou un env conda)."""
    if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
        return True
    conda = os.environ.get("CONDA_PREFIX")
    return bool(conda and Path(conda).resolve() == Path(sys.prefix).resolve())


def venv_python(venv_dir: Path) -> Path:
    """Chemin de l'exécutable Python d'un venv (Windows : Scripts/python.exe)."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _is_valid_venv(venv_dir: Path) -> bool:
    return (venv_dir / "pyvenv.cfg").is_file() and venv_python(venv_dir).is_file()


def _config_venv_dir() -> Optional[Path]:
    """Venv mémorisé dans shadow_match.config.json (clé "venv" -> "dir")."""
    cfg_file = os.environ.get("SHADOWMATCH_CONFIG")
    p = Path(cfg_file).expanduser() if cfg_file else PROJECT_ROOT / "shadow_match.config.json"
    try:
        d = (json.loads(p.read_text(encoding="utf-8")).get("venv") or {}).get("dir")
        return Path(d) if d else None
    except (OSError, ValueError, AttributeError):
        return None


def find_venv() -> Optional[Path]:
    """
    Ordre : $SHADOWMATCH_VENV -> venv de la config -> .venv / venv / env à la racine du projet.
    Retourne le dossier du venv (valide) ou None.
    """
    candidates = []
    env = os.environ.get("SHADOWMATCH_VENV")
    if env:
        candidates.append(Path(env).expanduser())
    cfg = _config_venv_dir()
    if cfg:
        candidates.append(cfg)
    candidates += [PROJECT_ROOT / n for n in DEFAULT_VENV_NAMES]
    for c in candidates:
        if _is_valid_venv(c):
            return c.resolve()
    return None


def _same_env(venv_dir: Path) -> bool:
    """True si le Python courant EST celui de ce venv."""
    try:
        return Path(sys.prefix).resolve() == venv_dir.resolve()
    except OSError:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Relance automatique dans le venv
# ══════════════════════════════════════════════════════════════════════════════
def maybe_reexec_in_venv(argv: Optional[list] = None) -> None:
    """
    À appeler tout en haut de main.py. Si un venv du projet existe et qu'on n'est pas
    déjà dedans, relance `main.py <args>` avec son Python et ne revient pas.
    Sans effet si : déjà dans un venv, SHADOWMATCH_NO_VENV=1, ou aucun venv trouvé.
    """
    if os.environ.get("SHADOWMATCH_NO_VENV", "").lower() in ("1", "true", "yes"):
        return
    if os.environ.get(REEXEC_FLAG) or in_venv():
        return
    vdir = find_venv()
    if vdir is None or _same_env(vdir):
        return

    py = str(venv_python(vdir))
    args = [py] + (argv if argv is not None else sys.argv)
    env = os.environ.copy()
    env[REEXEC_FLAG] = "1"          # anti-boucle
    env["VIRTUAL_ENV"] = str(vdir)
    print(f"[venv] Relance dans {vdir}", flush=True)

    if os.name == "nt":             # os.execv casse la console sous Windows
        sys.exit(subprocess.call(args, env=env))
    os.environ.update(env)
    os.execv(py, args)


# ══════════════════════════════════════════════════════════════════════════════
#  Création / installation
# ══════════════════════════════════════════════════════════════════════════════
def _run(cmd: list, log: LogFn, cwd: Optional[Path] = None) -> int:
    """Lance une commande, affiche sa sortie en direct (pip, playwright...)."""
    log(f"$ {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(
            [str(c) for c in cmd], cwd=str(cwd or PROJECT_ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except OSError as e:
        log(f"✖ {e}")
        return 1
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log(f"  {line}")
    return proc.wait()


def create_venv(venv_dir: Path, log: LogFn = print) -> bool:
    """Crée le venv (avec pip). Sur Debian/Ubuntu sans python3-venv, explique quoi faire."""
    log(f"◆ Création du venv : {venv_dir}")
    try:
        _venv.EnvBuilder(with_pip=True, clear=False, upgrade_deps=False).create(str(venv_dir))
    except Exception as e:           # ensurepip absent => python3-venv manquant
        log(f"✖ Création du venv impossible : {e}")
        if os.name != "nt":
            log("  Debian / Ubuntu / Kali :  sudo apt install python3-venv python3-pip")
        return False
    if not _is_valid_venv(venv_dir):
        log("✖ Venv créé mais Python introuvable dedans.")
        return False
    log("✔ Venv créé")
    return True


def setup(
    venv_dir: Optional[str] = None,
    requirements: str = "requirements.txt",
    skip_requirements: bool = False,
    use_current_python: bool = False,
    log: LogFn = print,
) -> int:
    """
    Prépare TOUT l'environnement. Retourne un code de sortie (0 = OK).
    Réutilise le venv actif si on est déjà dans un venv (aucun venv imbriqué).
    """
    log("═" * 54)
    log("SHADOW-MATCH — setup (venv + dépendances + Playwright)")
    log("═" * 54)
    log(f"Python hôte : {sys.executable}  ({sys.version.split()[0]})")

    # 1) Choix / création du venv ─────────────────────────────────────────────────
    explicit = Path(venv_dir).expanduser() if venv_dir else None
    if use_current_python:
        vdir, py = None, Path(sys.executable)
        log(f"↷ --no-venv : installation dans le Python courant ({py})")
        if not in_venv():
            log("  ⚠ Ce Python n'est pas un venv : sur Kali/Debian/Ubuntu, pip peut refuser (PEP 668).")
    elif explicit is None and in_venv():
        vdir = Path(sys.prefix)
        py = Path(sys.executable)
        log(f"✔ Venv actif détecté, réutilisé : {vdir}")
    else:
        vdir = (explicit or find_venv() or PROJECT_ROOT / DEFAULT_CREATE_NAME).resolve()
        if _is_valid_venv(vdir):
            log(f"✔ Venv existant : {vdir}")
        elif not create_venv(vdir, log):
            return 1
        py = venv_python(vdir)

    # 2) Dépendances Python ─────────────────────────────────────────────────────
    rc = 0
    req = (PROJECT_ROOT / requirements) if not Path(requirements).is_absolute() else Path(requirements)
    if skip_requirements:
        log("↷ Installation des requirements ignorée (--skip-requirements)")
    elif not req.is_file():
        log(f"✖ Fichier introuvable : {req}")
        rc = 1
    else:
        _run([py, "-m", "pip", "install", "--upgrade", "pip"], log)
        rc = _run([py, "-m", "pip", "install", "-r", req], log)
        if rc != 0:
            log("✖ pip install -r a échoué (voir ci-dessus). Playwright est quand même configuré.")
            log("  insightface demande souvent un compilateur C++ "
                "(Windows : Build Tools for Visual Studio ; Linux : build-essential python3-dev).")

    # 3) Playwright + Chromium AVEC le Python du venv ─────────────────────────────
    #    (sous-processus : sys.executable y vaut alors le Python du venv)
    if vdir is not None:
        os.environ["SHADOWMATCH_VENV"] = str(vdir)
    pw_rc = _run([py, "-m", "core.playwright_setup", "--reset"], log)

    # 4) Mémorise le venv dans shadow_match.config.json ────────────────────────────
    if vdir is not None:
        _remember_venv(vdir, py, log)

    ok = rc == 0 and pw_rc == 0
    log("")
    log("✔ SETUP TERMINÉ" if ok else "⚠ SETUP TERMINÉ AVEC DES ERREURS")
    if vdir is not None:
        act = (f"{vdir}\\Scripts\\activate" if os.name == "nt" else f"source {vdir}/bin/activate")
        log(f"  Activer le venv (optionnel) : {act}")
    log("  Lancer : python main.py --image cible.jpg   (relance auto dans le venv)")
    return 0 if ok else 1


def _remember_venv(vdir: Path, py: Path, log: LogFn) -> None:
    cfg_file = os.environ.get("SHADOWMATCH_CONFIG")
    p = Path(cfg_file).expanduser() if cfg_file else PROJECT_ROOT / "shadow_match.config.json"
    try:
        cfg = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["venv"] = {
            "dir": str(vdir),
            "python": str(py),
            "created_at": cfg.get("venv", {}).get("created_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"✔ Venv enregistré -> {p}")
    except OSError as e:
        log(f"⚠ Impossible d'écrire la config : {e}")
