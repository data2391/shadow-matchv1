#!/usr/bin/env python3
import sys
import os

# Ajoute la racine du projet au path pour les imports relatifs
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from cli.interface import splash_screen, print_status

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
    args = parser.parse_args()

    if args.web:
        from web.server import run_server
        run_server()
        return

    if not args.image and not args.dir:
        parser.print_help()
        sys.exit(1)

    from core.face_engine import FaceEngine
    from core.yandex_scraper import YandexScraper
    from core.cleanup import CleanupManager

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
