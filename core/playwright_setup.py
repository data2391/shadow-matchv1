"""
core/playwright_setup.py  —  Détection / installation / configuration de Playwright

Corrige l'erreur :
    BrowserType.launch: Executable doesn't exist at ~/.cache/ms-playwright/chromium-XXXX/chrome-linux64/chrome
    Looks like Playwright was just installed or updated. Please run: playwright install

Ce que fait ce module :
  1. Détecte le paquet Python `playwright` (et sa version) -> pip install si absent
     (uniquement dans un venv, cf. core/venv_bootstrap.py ; jamais dans le Python système).
  2. Détecte le répertoire des navigateurs Playwright (PLAYWRIGHT_BROWSERS_PATH, sinon
     chemin par défaut Windows / macOS / Linux) et le chemin EXACT de chromium attendu
     par la version de Playwright installée.
  3. Si chromium est absent -> `<python-du-venv> -m playwright install chromium`
     (utilise sys.executable, donc le bon venv, jamais le Playwright système).
  4. Repli sur un navigateur système (Chrome / Chromium / Edge / Brave) si l'install échoue.
  5. Écrit toute la configuration détectée dans `shadow_match.config.json`
     (racine du projet) — fichier modifiable à la main pour forcer un chemin.

Ordre de résolution du navigateur :
  1. variable d'env SHADOWMATCH_BROWSER_PATH
  2. "browser_path_override" dans shadow_match.config.json
  3. Chromium géré par Playwright (installé si besoin)
  4. Navigateur système détecté

Variables d'environnement utiles :
  SHADOWMATCH_BROWSER_PATH   chemin forcé vers un exécutable chrome/chromium
  SHADOWMATCH_AUTO_INSTALL   0 / false pour désactiver pip + playwright install auto
  SHADOWMATCH_CONFIG         chemin alternatif du fichier de configuration
  PLAYWRIGHT_BROWSERS_PATH   répertoire des navigateurs Playwright (standard Playwright)

CLI :  python -m core.playwright_setup [--check] [--no-install] [--reset]
       python main.py --setup
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILENAME = "shadow_match.config.json"
CONFIG_SCHEMA = 1

# Probe lancé dans un sous-processus : l'API sync de Playwright est interdite dans une
# boucle asyncio (serveur FastAPI), le sous-processus évite ce problème.
_PROBE_CODE = r"""
import json, os
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    exe = p.chromium.executable_path
print(json.dumps({"executable_path": exe, "exists": bool(exe and os.path.exists(exe))}))
"""

LogFn = Callable[[str], None]


# ══════════════════════════════════════════════════════════════════════════════
#  Configuration (shadow_match.config.json)
# ══════════════════════════════════════════════════════════════════════════════
def config_path() -> Path:
    env = os.environ.get("SHADOWMATCH_CONFIG")
    return Path(env).expanduser() if env else PROJECT_ROOT / CONFIG_FILENAME


def load_config() -> dict:
    p = config_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> bool:
    cfg["schema"] = CONFIG_SCHEMA
    try:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def _auto_install_enabled(cfg: Optional[dict] = None) -> bool:
    env = os.environ.get("SHADOWMATCH_AUTO_INSTALL")
    if env is not None:
        return env.strip().lower() not in ("0", "false", "no", "off", "")
    return bool((cfg or load_config()).get("auto_install", True))


# ══════════════════════════════════════════════════════════════════════════════
#  Détection du paquet Playwright
# ══════════════════════════════════════════════════════════════════════════════
def playwright_package_version() -> Optional[str]:
    """Version du paquet `playwright` dans l'interpréteur courant, ou None."""
    if importlib.util.find_spec("playwright") is None:
        return None
    try:
        return metadata.version("playwright")
    except metadata.PackageNotFoundError:
        return "unknown"


def ensure_playwright_package(log: LogFn = print, auto_install: Optional[bool] = None) -> Optional[str]:
    """Garantit que le paquet Python `playwright` est importable (pip install sinon)."""
    version = playwright_package_version()
    if version:
        return version
    if auto_install is None:
        auto_install = _auto_install_enabled()
    if not auto_install:
        log("✖ Paquet Python 'playwright' absent -> pip install playwright")
        return None

    # Jamais de pip dans le Python système (PEP 668 sur Kali/Debian/Ubuntu + pollution) :
    # on n'installe automatiquement que dans un venv.
    from core.venv_bootstrap import in_venv
    if not in_venv():
        log("✖ Paquet Python 'playwright' absent et aucun venv actif.")
        log("  Lance :  python main.py --setup   (crée .venv, installe tout, configure Chromium)")
        return None

    log("⚠ Paquet 'playwright' absent — installation (pip, dans le venv)...")
    rc = _run([sys.executable, "-m", "pip", "install", "playwright>=1.42.0"], log)
    importlib.invalidate_caches()
    version = playwright_package_version()
    if rc != 0 or not version:
        log("✖ pip install playwright a échoué. Si le système est 'externally-managed' "
            "(Kali / Debian), utilise un venv : python3 -m venv venv && source venv/bin/activate")
        return None
    log(f"✔ playwright {version} installé")
    return version


# ══════════════════════════════════════════════════════════════════════════════
#  Détection du répertoire des navigateurs
# ══════════════════════════════════════════════════════════════════════════════
def default_browsers_dir() -> Path:
    """
    Répertoire où Playwright range ses navigateurs (même logique que Playwright) :
      PLAYWRIGHT_BROWSERS_PATH=0  -> <site-packages>/playwright/driver/package/.local-browsers
      PLAYWRIGHT_BROWSERS_PATH=X  -> X
      sinon  Windows %LOCALAPPDATA%\\ms-playwright | macOS ~/Library/Caches/ms-playwright
             Linux  $XDG_CACHE_HOME ou ~/.cache /ms-playwright
    """
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env == "0":
        spec = importlib.util.find_spec("playwright")
        if spec and spec.origin:
            return Path(spec.origin).parent / "driver" / "package" / ".local-browsers"
    elif env:
        return Path(env).expanduser()

    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ms-playwright"
    if system == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "ms-playwright"


def list_installed_browsers(browsers_dir: Optional[Path] = None) -> list:
    """Liste les dossiers navigateurs présents (chromium-1217, firefox-..., ...)."""
    d = browsers_dir or default_browsers_dir()
    try:
        return sorted(p.name for p in d.iterdir() if p.is_dir())
    except OSError:
        return []


def probe_playwright_chromium(timeout: int = 40) -> dict:
    """
    Demande à Playwright (dans un sous-processus) le chemin EXACT de chromium attendu
    pour SA version, et vérifie qu'il existe.
    -> {"executable_path": str|None, "exists": bool, "error": str|None}
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE_CODE],
            capture_output=True, text=True, timeout=timeout,
            env=os.environ.copy(),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            data["error"] = None
            return data
        err = (proc.stderr or proc.stdout or "probe failed").strip().splitlines()
        return {"executable_path": None, "exists": False, "error": err[-1] if err else "probe failed"}
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        return {"executable_path": None, "exists": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  Navigateurs système (repli)
# ══════════════════════════════════════════════════════════════════════════════
def find_system_browser() -> Optional[str]:
    """Cherche Chrome / Chromium / Edge / Brave déjà installé sur la machine."""
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
             "chrome", "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave"]
    for n in names:
        found = shutil.which(n)
        if found:
            return found

    system = platform.system()
    candidates: list = []
    if system == "Windows":
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for r in filter(None, roots):
            candidates += [
                Path(r) / "Google/Chrome/Application/chrome.exe",
                Path(r) / "Microsoft/Edge/Application/msedge.exe",
                Path(r) / "BraveSoftware/Brave-Browser/Application/brave.exe",
                Path(r) / "Chromium/Application/chrome.exe",
            ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
        ]
    else:
        candidates = [Path(p) for p in (
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
            "/snap/bin/chromium", "/opt/google/chrome/chrome",
        )]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Installation
# ══════════════════════════════════════════════════════════════════════════════
def _run(cmd: list, log: LogFn, timeout: int = 900) -> int:
    """Lance une commande en relayant sa sortie ligne par ligne vers `log`."""
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=os.environ.copy(),
        )
    except OSError as e:
        log(f"✖ Impossible de lancer {' '.join(cmd)} : {e}")
        return 1

    start, last = time.time(), ""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            # la barre de progression Playwright réécrit la même ligne : on filtre le bruit
            if line and line != last and "|" not in line[:3]:
                log(f"  {line}")
                last = line
            if time.time() - start > timeout:
                proc.kill()
                log("✖ Timeout d'installation dépassé")
                return 1
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()


def install_chromium(log: LogFn = print, with_deps: Optional[bool] = None) -> bool:
    """
    `python -m playwright install chromium` avec l'interpréteur COURANT (venv respecté).
    Sous Linux en root, ajoute --with-deps pour tirer les libs système (libnss3, ...).
    """
    if with_deps is None:
        with_deps = (
            platform.system() == "Linux"
            and hasattr(os, "geteuid") and os.geteuid() == 0
        )
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    if with_deps:
        cmd.append("--with-deps")
    log(f"⬇ Installation de Chromium : {' '.join(cmd)}")
    rc = _run(cmd, log)
    if rc != 0 and with_deps:
        log("⚠ --with-deps a échoué — nouvelle tentative sans les dépendances système...")
        rc = _run([sys.executable, "-m", "playwright", "install", "chromium"], log)
    return rc == 0


# ══════════════════════════════════════════════════════════════════════════════
#  API principale
# ══════════════════════════════════════════════════════════════════════════════
def ensure_browser(
    log: LogFn = print,
    auto_install: Optional[bool] = None,
    force_check: bool = False,
) -> dict:
    """
    Détecte tout, installe ce qui manque, écrit la config, et retourne :
      {
        "ok": bool,
        "source": "override" | "playwright" | "system" | None,
        "executable_path": str | None,   # None => laisser Playwright choisir lui-même
        "playwright_version": str | None,
        "browsers_dir": str,
        "installed_browsers": [...],
        ...
      }
    Appel rapide si la config en cache est toujours valide (aucun sous-processus).
    """
    cfg = load_config()
    if auto_install is None:
        auto_install = _auto_install_enabled(cfg)

    # 0) Chemin forcé par l'utilisateur ───────────────────────────────────────────
    forced = os.environ.get("SHADOWMATCH_BROWSER_PATH") or cfg.get("browser_path_override")
    if forced:
        forced = str(Path(forced).expanduser())
        if Path(forced).is_file():
            return {**_base_info(cfg), "ok": True, "source": "override", "executable_path": forced}
        log(f"⚠ Chemin navigateur forcé introuvable : {forced} — détection automatique.")

    # 1) Cache de configuration encore valide ? ───────────────────────────────────
    pw_version = playwright_package_version()
    cached = cfg.get("browser") or {}
    if (
        not force_check
        and pw_version
        and cached.get("playwright_version") == pw_version
        and cached.get("executable_path")
        and Path(cached["executable_path"]).is_file()
    ):
        return {**_base_info(cfg), "ok": True, "source": cached.get("source", "playwright"),
                "executable_path": cached["executable_path"] if cached.get("source") == "system" else None,
                "playwright_version": pw_version}

    # 2) Paquet Python ───────────────────────────────────────────────────────────
    pw_version = ensure_playwright_package(log, auto_install)

    browsers_dir = default_browsers_dir()
    info = {
        "ok": False, "source": None, "executable_path": None,
        "playwright_version": pw_version,
        "browsers_dir": str(browsers_dir),
        "browsers_dir_exists": browsers_dir.is_dir(),
        "installed_browsers": list_installed_browsers(browsers_dir),
        "python": sys.executable,
        "platform": f"{platform.system()} {platform.machine()}",
    }

    resolved_path: Optional[str] = None
    if pw_version:
        probe = probe_playwright_chromium()
        info["expected_chromium_path"] = probe.get("executable_path")
        if probe["exists"]:
            info.update(ok=True, source="playwright")
            resolved_path = probe["executable_path"]
            log(f"✔ Chromium Playwright détecté : {resolved_path}")
        else:
            expected = probe.get("executable_path") or "(inconnu)"
            log(f"⚠ Chromium Playwright introuvable : {expected}")
            log(f"  Répertoire navigateurs : {browsers_dir} "
                f"({'existe' if browsers_dir.is_dir() else 'absent'})")
            if auto_install:
                if install_chromium(log):
                    probe = probe_playwright_chromium()
                    info["installed_browsers"] = list_installed_browsers(browsers_dir)
                    if probe["exists"]:
                        info.update(ok=True, source="playwright")
                        resolved_path = probe["executable_path"]
                        log(f"✔ Chromium installé : {resolved_path}")
                else:
                    log("✖ L'installation de Chromium a échoué.")
            else:
                log("  Auto-install désactivé -> lance : "
                    f"{sys.executable} -m playwright install chromium")

    # 3) Repli : navigateur système ───────────────────────────────────────────────
    if not info["ok"]:
        sysb = find_system_browser()
        if sysb:
            log(f"↪ Repli sur le navigateur système : {sysb}")
            info.update(ok=True, source="system", executable_path=sysb)
            resolved_path = sysb
        else:
            log("✖ Aucun navigateur utilisable. Solutions :")
            log(f"    1) {sys.executable} -m playwright install chromium")
            log("    2) installer Google Chrome / Chromium")
            log(f"    3) renseigner 'browser_path_override' dans {config_path()}")

    # 4) Persistance dans le fichier de configuration ───────────────────────────
    cfg.setdefault("auto_install", True)
    cfg.setdefault("browser_path_override", None)
    cfg["browser"] = {
        "ok": info["ok"],
        "source": info["source"],
        "executable_path": resolved_path,
        "playwright_version": pw_version,
        "browsers_dir": info["browsers_dir"],
        "installed_browsers": info["installed_browsers"],
        "python": sys.executable,
        "platform": info["platform"],
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if save_config(cfg):
        info["config_file"] = str(config_path())
        log(f"✔ Configuration enregistrée -> {config_path()}")
    return info


def _base_info(cfg: dict) -> dict:
    b = cfg.get("browser") or {}
    return {
        "playwright_version": playwright_package_version(),
        "browsers_dir": b.get("browsers_dir") or str(default_browsers_dir()),
        "installed_browsers": b.get("installed_browsers", []),
        "config_file": str(config_path()),
    }


async def ensure_browser_async(log=None, **kwargs) -> dict:
    """
    Version asynchrone : exécute la détection/installation dans un thread pour ne pas
    bloquer l'event loop (FastAPI / WebSocket). `log` peut être sync ou async.
    """
    loop = asyncio.get_running_loop()

    def _thread_log(msg: str):
        print(msg, flush=True)
        if log is None:
            return
        if asyncio.iscoroutinefunction(log):
            asyncio.run_coroutine_threadsafe(log(msg), loop)
        else:
            loop.call_soon_threadsafe(log, msg)

    return await loop.run_in_executor(None, lambda: ensure_browser(_thread_log, **kwargs))


def is_missing_browser_error(exc: BaseException) -> bool:
    """True si l'exception est le classique "Executable doesn't exist ... playwright install"."""
    msg = str(exc)
    return (
        "Executable doesn't exist" in msg
        or "playwright install" in msg
        or "download new browsers" in msg
    )


async def launch_chromium(pw, headless: bool = False, args: Optional[list] = None, log=None):
    """
    Remplace `pw.chromium.launch(...)` : lance Chromium avec le bon exécutable et, si
    Playwright répond "Executable doesn't exist", installe le navigateur puis relance.

        async with async_playwright() as pw:
            browser = await launch_chromium(pw, headless=False, args=[...])
    """
    info = await ensure_browser_async(log)
    kwargs: dict = {"headless": headless}
    if args:
        kwargs["args"] = args
    if info.get("executable_path"):
        kwargs["executable_path"] = info["executable_path"]

    try:
        return await pw.chromium.launch(**kwargs)
    except Exception as e:
        if not is_missing_browser_error(e):
            raise
        # Détection OK mais le lancement échoue encore (ex. headless-shell manquant) :
        # on force une réinstallation puis une dernière tentative.
        msg = "⚠ Lancement refusé (navigateur manquant) — réinstallation forcée..."
        print(msg, flush=True)
        if log:
            r = log(msg)
            if asyncio.iscoroutine(r):
                await r
        if not _auto_install_enabled():
            raise
        loop = asyncio.get_running_loop()
        ok = await loop.run_in_executor(None, lambda: install_chromium(print))
        if not ok:
            raise
        info = await ensure_browser_async(log, force_check=True)
        kwargs.pop("executable_path", None)
        if info.get("source") == "system" and info.get("executable_path"):
            kwargs["executable_path"] = info["executable_path"]
        return await pw.chromium.launch(**kwargs)


# ══════════════════════════════════════════════════════════════════════════════
#  Diagnostic (affiché par `main.py --setup` et /debug)
# ══════════════════════════════════════════════════════════════════════════════
def _venv_label() -> str:
    from core.venv_bootstrap import in_venv, find_venv
    if in_venv():
        return f"oui ({sys.prefix})"
    found = find_venv()
    return f"non — venv du projet trouvé : {found}" if found else "non — aucun venv (python main.py --setup)"


def diagnostic_lines() -> list:
    cfg = load_config()
    b = cfg.get("browser") or {}
    bd = default_browsers_dir()
    return [
        f"Python            : {sys.executable}",
        f"Venv actif        : {_venv_label()}",
        f"Playwright (pkg)  : {playwright_package_version() or 'MISSING'}",
        f"Browsers dir      : {bd}  exists={bd.is_dir()}",
        f"Installed         : {', '.join(list_installed_browsers(bd)) or '-'}",
        f"Chromium résolu   : {b.get('executable_path') or b.get('source') or '-'}",
        f"Système (repli)   : {find_system_browser() or '-'}",
        f"Config            : {config_path()}  exists={config_path().is_file()}",
        f"Auto-install      : {_auto_install_enabled(cfg)}",
    ]


def main(argv: Optional[list] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="SHADOW-MATCH — setup Playwright")
    ap.add_argument("--check", action="store_true", help="diagnostic seulement, rien n'est installé")
    ap.add_argument("--no-install", action="store_true", help="détecte sans rien installer")
    ap.add_argument("--reset", action="store_true", help="ignore le cache et re-détecte tout")
    a = ap.parse_args(argv)

    if a.check:
        print("\n".join(diagnostic_lines()))
        return 0
    info = ensure_browser(print, auto_install=False if a.no_install else None, force_check=a.reset)
    print()
    print("\n".join(diagnostic_lines()))
    print(f"\n=> {'OK' if info['ok'] else 'ECHEC'} (source: {info['source']})")
    return 0 if info["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
