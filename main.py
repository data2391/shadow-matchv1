#!/usr/bin/env python3
import sys
import os

# Ajoute la racine du projet au path pour les imports relatifs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse

# ── Venv / setup : AVANT tout import de dépendance tierce (rich, playwright, insightface...) ──
# core.venv_bootstrap n'utilise que la stdlib : il peut créer le venv puis relancer l'outil dedans.
from core import venv_bootstrap

if "--no-venv" in sys.argv:
    os.environ["SHADOWMATCH_NO_VENV"] = "1"

if "--setup" in sys.argv:
    _p = argparse.ArgumentParser(add_help=False)
    _p.add_argument("--setup", action="store_true")
    _p.add_argument("--no-venv", action="store_true")
    _p.add_argument("--venv-dir")
    _p.add_argument("--requirements", default="requirements.txt")
    _p.add_argument("--skip-requirements", action="store_true")
    _a, _ = _p.parse_known_args()
    sys.exit(venv_bootstrap.setup(
        venv_dir=_a.venv_dir,
        requirements=_a.requirements,
        skip_requirements=_a.skip_requirements,
        use_current_python=_a.no_venv,
    ))

# Un venv du projet existe et on n'est pas dedans -> on relance main.py avec son Python.
venv_bootstrap.maybe_reexec_in_venv()

try:
    from cli.interface import splash_screen, print_status
except ModuleNotFoundError as _e:
    print(f"✖ Dépendance manquante : {_e.name}\n"
          f"  Lance d'abord :  python main.py --setup   (crée .venv + installe tout + Chromium)")
    sys.exit(1)

def _missing_dependency(exc):
    """Dépendance absente : message clair au lieu d'une trace Python."""
    print_status(f"Dépendance manquante : {exc.name}", "error")
    print_status("Lance :  python main.py --setup   (crée .venv, installe tout + Chromium)", "warning")
    sys.exit(1)


def main():
    splash_screen()
    print("\n" + "="*50)
    print("🚀 SHADOW-MATCH OSINT ENGINE".center(50))
    print("🔥 Coded by Data2391".center(50))
    print("="*50 + "\n")


    parser = argparse.ArgumentParser(description="SHADOW-MATCH — OSINT Facial Recognition Engine")
    parser.add_argument("--image", "-i",  help="Target image path")
    parser.add_argument("--dir",   "-d",  help="Directory of target images (batch mode)")
    parser.add_argument("--web",   action="store_true", help="Launch web dashboard")
    parser.add_argument("--stealth", "-S", action="store_true",
                        help="Stealth mode: in-memory processing, zero disk traces")
    parser.add_argument("--model", "-m", choices=["buffalo_l", "buffalo_s"],
                        default="buffalo_l",
                        help="InsightFace model: buffalo_l (precise) | buffalo_s (fast batch)")
    parser.add_argument("--threshold", "-t", type=float, default=0.45,
                        help="ArcFace distance threshold (default: 0.45)")
    parser.add_argument("--output", "-o", default="results",
                        help="Output folder for results JSON")
    parser.add_argument("--setup", action="store_true",
                        help="Crée .venv, installe requirements + Playwright + Chromium, écrit shadow_match.config.json")
    parser.add_argument("--venv-dir", metavar="DIR",
                        help="Dossier du venv pour --setup (défaut : .venv, ou venv/env s'ils existent)")
    parser.add_argument("--requirements", metavar="FILE", default="requirements.txt",
                        help="Fichier de dépendances pour --setup (défaut : requirements.txt)")
    parser.add_argument("--skip-requirements", action="store_true",
                        help="--setup : ne pas lancer pip install -r (Playwright/Chromium seulement)")
    parser.add_argument("--no-venv", action="store_true",
                        help="Ne pas utiliser de venv : travaille avec le Python courant")
    parser.add_argument("--browser-path", metavar="PATH",
                        help="Force l'exécutable Chrome/Chromium à utiliser (sauvegardé dans la config)")
    parser.add_argument("--no-auto-install", action="store_true",
                        help="Ne jamais installer automatiquement playwright / chromium")
    args = parser.parse_args()

    if args.no_auto_install:
        os.environ["SHADOWMATCH_AUTO_INSTALL"] = "0"

    if args.browser_path:
        from core import playwright_setup as pws
        if not os.path.isfile(args.browser_path):
            print_status(f"Chemin introuvable : {args.browser_path}", "error")
            sys.exit(1)
        cfg = pws.load_config()
        cfg["browser_path_override"] = os.path.abspath(args.browser_path)
        pws.save_config(cfg)
        print_status(f"Navigateur forcé enregistré dans {pws.config_path()}", "success")

    if args.web:
        try:
            from web.server import run_server
        except ModuleNotFoundError as e:
            _missing_dependency(e)
        run_server()
        return

    if not args.image and not args.dir:
        parser.print_help()
        sys.exit(1)

    try:
        from core.face_engine import FaceEngine
        from core.yandex_scraper import YandexScraper
        from core.cleanup import CleanupManager
    except ModuleNotFoundError as e:
        _missing_dependency(e)

    # Nettoyage uploads au démarrage
    upload_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "uploads")
    CleanupManager(upload_path, max_age_hours=2).run()

    engine  = FaceEngine(model_name=args.model)
    scraper = YandexScraper(stealth=args.stealth)

    if args.image:
        print_status(f"[TARGET] Loading image: {args.image}")
        results = engine.process_single(
            image_path=args.image,
            scraper=scraper,
            threshold=args.threshold,
            stealth=args.stealth
        )
        engine.print_results(results)

        # --- PRO FIX: SAUVEGARDE SINGLE RUN DANS DOSSIER OUT ---
        if results:
            import json, time
            from pathlib import Path
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"shadow_match_{int(time.time())}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump({"target": args.image, "results": results}, f, indent=2)
            print_status(f"Résultats sauvegardés dans -> {out_file}", "success")

    elif args.dir:
        print_status(f"[BATCH] Scanning directory: {args.dir}")
        if args.model == "buffalo_l":
            print_status("[WARN] buffalo_l sur 500+ images = CPU en feu. Utilise --model buffalo_s", "warning")
        engine.process_directory(
            dir_path=args.dir,
            scraper=scraper,
            threshold=args.threshold,
            stealth=args.stealth,
            output_dir=args.output
        )

if __name__ == "__main__":
    main()
