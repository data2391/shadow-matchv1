<div align="center">

```
 _____ _               _           __  __       _       _       _
/ ____| |             | |         |  \/  |     | |     | |     | |
| (___ | |__   __ _  __| | _____      | \  / | __ _| |_ ___| |__   | |
 \___ \| '_ \ / _` |/ _` |/ _ \ \  | |\/| |/ _` | __/ __| '_ \  | |
 ____) | | | | (_| | (_| | (_) |  | |  | | (_| | || (__| | | | |_|
|_____/|_| |_|\__,_|\__,_|\___/   |_|  |_|\__,_|\__\___|_| |_| (_)
                                           v1  —  by  Data2391
```

**OSINT Facial Recognition Engine**

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-Apache_2.0-green?style=flat-square)
![InsightFace](https://img.shields.io/badge/AI-InsightFace_ArcFace-red?style=flat-square)
![Playwright](https://img.shields.io/badge/Scraping-Playwright-orange?style=flat-square)

</div>

---

## Presentation

SHADOW-MATCH est un meta-moteur de reconnaissance faciale OSINT 100% local.  
Il combine la vision par ordinateur de pointe (**InsightFace ArcFace**) avec un scraping web de niveau militaire (**Playwright + bypass anti-bot Yandex**) pour identifier automatiquement une cible a partir d'une simple photo.

**Zero API payante. Zero cloud. Zero trace. Ton hardware, tes regles.**

---

## Quick Start

```bash
# 1. Installation en UNE commande : cree .venv, installe requirements.txt + Playwright + Chromium + modele AdaFace
python main.py --setup

# 2. Mode CLI — image unique (relance automatiquement dans .venv, pas besoin de l'activer)
python main.py --image target.jpg

# 3. Mode CLI — dossier batch (buffalo_s = plus leger)
python main.py -d ./targets --model buffalo_s

# 4. Mode Furtif — zero trace disque
python main.py --image target.jpg -S

# 5. Web Dashboard (http://localhost:8080)
python main.py --web
```

---

## Venv, Playwright et configuration

### Pourquoi un venv

Kali, Debian et Ubuntu recents refusent `pip install` hors venv (`externally-managed-environment`, PEP 668),
et `playwright install` doit etre lance avec le meme Python que celui qui execute l'outil.
SHADOW-MATCH gere donc tout dans un venv du projet (`core/venv_bootstrap.py`) :

- `python main.py --setup` : cree `.venv` (ou reutilise `venv/`, `env/` ou le venv actif), fait `pip install -r requirements.txt`
  avec le pip **du venv**, installe Chromium avec le Python **du venv**, puis memorise le venv dans la config ;
- ensuite, `python main.py ...` lance depuis n'importe quel Python **se relance tout seul dans le venv** (aucune activation requise) ;
- `--no-venv` ou `SHADOWMATCH_NO_VENV=1` pour travailler avec le Python courant ;
- hors venv, l'outil n'execute **jamais** `pip install` dans le Python systeme : il t'indique `python main.py --setup`.

Manuel, si tu preferes :

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

### Erreur "Executable doesn't exist ... playwright install"

`BrowserType.launch: Executable doesn't exist at ~/.cache/ms-playwright/chromium-XXXX/...` est corrigee automatiquement
au lancement (`core/playwright_setup.py`) :

1. detecte le paquet `playwright` (pip install uniquement dans un venv) ;
2. detecte le dossier des navigateurs (`PLAYWRIGHT_BROWSERS_PATH`, sinon `~/.cache/ms-playwright`, `~/Library/Caches/ms-playwright` ou `%LOCALAPPDATA%\ms-playwright`) et le chemin exact de chromium attendu par ta version de Playwright ;
3. lance `<python du venv> -m playwright install chromium` si besoin (`--with-deps` auto sous Linux root) ;
4. se rabat sur Chrome / Chromium / Edge / Brave installe sur la machine si l'install echoue ;
5. ecrit tout dans `shadow_match.config.json` (ignore par git).

```bash
python main.py --setup                          # venv + dependances + Chromium + ecriture de la config
python main.py --setup --skip-requirements      # Playwright / Chromium seulement
python main.py --setup --venv-dir venv          # utiliser un autre dossier de venv
python main.py -i cible.jpg --browser-path /usr/bin/chromium   # forcer un navigateur
python main.py --no-auto-install ...            # ne jamais rien installer automatiquement
python -m core.playwright_setup --check         # diagnostic sans rien modifier
```

### Modele AdaFace ONNX (detection + telechargement auto)

Le module PRO charge `~/.insightface/models/adaface_ir101.onnx`. S'il manque, SHADOW-MATCH le telecharge tout seul
(`core/adaface_setup.py`) : au `--setup`, au demarrage de `--web` (avant l'ouverture du port, pour ne pas bloquer le dashboard)
et au chargement du moteur en CLI.

1. cherche le fichier : chemin force (`SHADOWMATCH_ADAFACE_PATH` / `--adaface-path`), puis `~/.insightface/models/` (noms `adaface_ir101.onnx`,
   `adaface_ir_101.onnx`, ...), puis `./models/` ;
2. le **valide** avec ONNX Runtime (entree 3x112x112, sortie 512D) ; un fichier tronque ou corrompu est mis de cote (`.invalid`) puis re-telecharge ;
3. sinon telecharge AdaFace IR-101 / WebFace12M (249 Mo) depuis GitHub (`yakhyo/adaface-onnx`, MIT), avec repli sur Hugging Face
   (`yakhyo/uniface-weights`) ; **reprise** si la connexion coupe, **controle SHA-256** (`f2eb07d0...a43e`), ecriture atomique : un fichier incomplet
   ou modifie n'est jamais utilise ;
4. ecrit le resultat dans la cle `adaface` de `shadow_match.config.json`.

```bash
python -m core.adaface_setup               # detecte / telecharge / valide
python -m core.adaface_setup --check       # diagnostic sans rien telecharger
python -m core.adaface_setup --path ~/mon_adaface.onnx   # utiliser un modele existant
python main.py --setup --skip-adaface      # setup sans AdaFace
SHADOWMATCH_ADAFACE=0 python main.py ...   # desactiver AdaFace completement
```

AdaFace est optionnel : s'il est indisponible, l'outil continue sans (`fusion desactivee`). `--no-auto-install` interdit aussi ce telechargement.
Le modele est tiers et n'est pas inclus dans le depot : verifie sa licence / ses conditions d'usage (AdaFace, Kim et al., CVPR 2022 ; donnees WebFace12M).

### Arch / BlackArch

`playwright install --with-deps` ne fonctionne qu'avec apt (Debian, Ubuntu, Kali) : sur Arch / BlackArch il est donc desactive
automatiquement. Si Chromium refuse de demarrer (`libnss3.so`, `libatk...` introuvable), installe les bibliotheques :

```bash
sudo pacman -S --needed nss nspr at-spi2-core cups libdrm mesa alsa-lib pango cairo libxkbcommon \
    libxcomposite libxdamage libxrandr libxfixes libx11 libxext libxcb dbus expat
# ou, plus simple : un Chromium systeme est detecte et utilise automatiquement en repli
sudo pacman -S chromium
```

Pour compiler `insightface` : `sudo pacman -S --needed base-devel python`.

`shadow_match.config.json` (modifiable a la main) :

```json
{
  "auto_install": true,
  "browser_path_override": null,
  "adaface": {
    "enabled": true,
    "path_override": null,
    "ok": true,
    "path": "/root/.insightface/models/adaface_ir101.onnx"
  },
  "venv": {
    "dir": "/home/user/shadow-matchv1/.venv",
    "python": "/home/user/shadow-matchv1/.venv/bin/python"
  },
  "browser": {
    "source": "playwright",
    "executable_path": "/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome",
    "playwright_version": "1.64.1",
    "browsers_dir": "/root/.cache/ms-playwright"
  }
}
```

Variables d'environnement : `SHADOWMATCH_VENV`, `SHADOWMATCH_NO_VENV`, `SHADOWMATCH_BROWSER_PATH`, `SHADOWMATCH_ADAFACE`, `SHADOWMATCH_ADAFACE_PATH`, `SHADOWMATCH_AUTO_INSTALL=0`, `SHADOWMATCH_CONFIG`.
Le dashboard (`/debug`) affiche aussi l'etat du venv, de Playwright et d'AdaFace.

---

## Architecture

```
shadow-matchv1/
|
+-- README.md                  # Fiche technique + Licence Apache 2.0
+-- main.py                    # Point d'entree : lance CLI ou serveur Web
+-- requirements.txt           # Dependances Python
|
+-- core/                      # LE CERVEAU (Moteurs IA et OSINT)
|   +-- __init__.py
|   +-- venv_bootstrap.py      # Creation / relance dans le venv (stdlib seule), --setup
|   +-- playwright_setup.py    # Detection/installation Playwright + chromium, config JSON
|   +-- adaface_setup.py       # Detection/telechargement/validation du modele AdaFace ONNX
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
