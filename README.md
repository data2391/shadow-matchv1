<div align="center">

```
 _____ _               _           __  __       _       _       _
/ ____| |             | |         |  \/  |     | |     | |     | |
| (___ | |__   __ _  __| | _____      | \  / | __ _| |_ ___| |__   | |
 \___ \| '_ \ / _` |/ _` |/ _ \ \  | |\/| |/ _` | __/ __| '_ \  | |
 ____) | | | | (_| | (_| | (_) |  | |  | | (_| | || (__| | | | |_|
|_____/|_| |_|\__,_|\__,_|\___/   |_|  |_|\__,_|\__\___|_| |_| (_)
                                         PRO  v1  —  by  Data2391
```

**OSINT Facial Recognition Engine**

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-Apache_2.0-green?style=flat-square)
![InsightFace](https://img.shields.io/badge/AI-InsightFace_ArcFace-red?style=flat-square)
![Playwright](https://img.shields.io/badge/Scraping-Playwright-orange?style=flat-square)

</div>

---

## Presentation

SHADOW-MATCH PRO est un meta-moteur de reconnaissance faciale OSINT 100% local.  
Il combine la vision par ordinateur de pointe (**InsightFace ArcFace**) avec un scraping web de niveau militaire (**Playwright + bypass anti-bot Yandex**) pour identifier automatiquement une cible a partir d'une simple photo.

**Zero API payante. Zero cloud. Zero trace. Ton hardware, tes regles.**

---

## Quick Start

```bash
# 1. Installer les dependances
pip install -r requirements.txt
playwight install chromium

# 2. Mode CLI — image unique
python main.py --image target.jpg

# 3. Mode CLI — dossier batch (buffalo_s = plus leger)
python main.py -d ./targets --model buffalo_s

# 4. Mode Furtif — zero trace disque
python main.py --image target.jpg -S

# 5. Web Dashboard (http://localhost:8080)
python main.py --web
```

---

## Architecture

```
ShadowMatch-PRO-Data2391/
|
+-- README.md                  # Fiche technique + Licence Apache 2.0
+-- main.py                    # Point d'entree : lance CLI ou serveur Web
+-- requirements.txt           # Dependances Python
|
+-- core/                      # LE CERVEAU (Moteurs IA et OSINT)
|   +-- __init__.py
|   +-- face_engine.py         # Coeur biometrique : ArcFace/AdaFace, embeddings 512D
|   +-- yandex_scraper.py      # Blindage anti-bot : Playwright + bypass FileChooser
|   +-- multi_engine.py        # Plan B : Google Lens, Bing Visual Search en fallback
|   +-- face_cropper.py        # Alignement et recadrage chirurgical des visages
|   +-- preprocessor.py        # Amelioration image (CLAHE, Denoising) pour photos floues
|   +-- cleanup.py             # Nettoyeur : efface les traces apres le scan
|
+-- cli/                       # LE TERMINAL (Interface Ligne de Commande)
|   +-- __init__.py
|   +-- interface.py           # Splash screen Rich, couleurs, tableaux de resultats
|
+-- web/                       # LE DASHBOARD (Interface Graphique)
    +-- __init__.py
    +-- server.py              # Backend FastAPI + WebSocket live feed
    +-- static/                # Assets CSS/JS externes (optionnel)
    +-- templates/
        +-- dashboard.html     # Interface cyberpunk : drag & drop, laser scan, galerie
```

---

## Comment ca marche — Les 4 Phases

### Phase 1 — Extraction Biometrique (InsightFace ArcFace)
L'outil ne compare pas des pixels. Le reseau de neurones **ResNet50** mappe le visage cible sur **512 dimensions mathematiques** (embedding). Lunettes, vieillissement, profil : l'empreinte reste quasi identique. **AdaFace** prend le relais si l'image est de mauvaise qualite.

### Phase 2 — Infiltration Bypass Anti-Bot (Yandex)
Yandex est le seul moteur qui n'a pas bride son algorithme de recherche faciale. Pour contourner son pare-feu **Cloudflare**, Playwright intercepte l'API OS `FileChooser` pour simuler un humain qui upload un fichier. **Indetectable.**

### Phase 3 — Extraction Visuelle (Hack V10)
Yandex cache les resultats dans des variables JSON cryptees. La solution : **lire l'ecran**. Le bot repere les images affichees, filtre les logos, simule un clic-droit humain pour copier l'URL source, et scrolle pour forcer le chargement de **50 resultats max**.

### Phase 4 — Filtrage ArcFace
Les 50 images rapatriees sont comparees localement avec l'empreinte originale. Si la **distance cosinus** est sous le seuil (defaut `0.45`), le match est confirme, exporte en JSON et affiche.

---

## Options CLI

| Option | Description |
|---|---|
| `-i / --image` | Image cible a scanner |
| `-d / --dir` | Mode batch : scanne tout un dossier |
| `-o / --output` | Dossier d'export des resultats JSON |
| `-t / --threshold` | Tolerance ArcFace (defaut : `0.45`, plus bas = plus strict) |
| `-S / --stealth` | Mode furtif : pipeline BytesIO, zero ecriture disque |
| `-m / --model` | Modele IA : `buffalo_l` (precis) ou `buffalo_s` (rapide) |
| `--web` | Lance le dashboard web sur `http://localhost:8080` |

**Exemple ultime :**
```bash
python main.py -i suspect.png -o Enquete01 -t 0.45 -S
```

---

## Fonctionnalites Cles

| Feature | Detail |
|---|---|
| **Captcha Handling** | Detection automatique du captcha Yandex, notification UI ou pause CLI |
| **Stealth Mode (-S)** | Pipeline BytesIO — zero image ecrite sur disque |
| **Auto-Cleanup** | Uploads de plus de 2h supprimes automatiquement au demarrage |
| **Engine Fallback** | Si Yandex < 3 resultats, bascule sur Google Lens puis Bing |
| **Live Feed** | Playwright --> WebSocket --> Dashboard en temps reel |
| **ArcFace Threshold** | Defaut `0.45` — configurable via `--threshold` ou interface web |
| **Multi-Model** | `buffalo_l` (precision max) / `buffalo_s` (batch rapide, CPU-friendly) |

---

## Licence

Distribue sous **Licence Apache 2.0**.  
Utilisation libre, modification libre, integration commerciale libre.  
La responsabilite de l'usage appartient entierement a l'utilisateur.  
Conserver les notices de droits d'auteur originales lors de toute redistribution.

---

<div align="center">
<sub>Coded by <b>Data2391</b> — OSINT Facial Recognition Engine — Apache 2.0</sub>
</div>
