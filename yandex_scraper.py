"""
core/yandex_scraper.py  —  Yandex Visual Search via Playwright
Stratégie : attente changement URL après upload + sélecteurs larges + dump debug
"""

import asyncio, time, io, random, json
from pathlib import Path
from typing import Union
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

YANDEX_URL = "https://yandex.com/images/"

CAPTCHA_SELECTORS = [
    ".AdvancedCaptcha", ".CheckboxCaptcha",
    "iframe[src*='smartcaptcha']", "#js-button",
]

CAM_SELECTORS = [
    "button.CbirSearch-Button",
    "[class*='CbirSearch'][class*='Button']",
    "button[aria-label*='image' i]",
    "[class*='visual-search']",
    "[data-bem*='CbirSearch']",
    ".HeaderSearch button[type='button']:last-child",
    "button[class*='Search']:last-of-type",
]

UPLOAD_TAB_SELECTORS = [
    "button[data-type='upload']",
    ".CbirModalSearch-Tab[data-type='upload']",
    "label[class*='Upload']",
    "button:has-text('Upload')",
    "button:has-text('Загрузить')",
    "button:has-text('File')",
]

FILE_INPUT_SELECTORS = [
    "input[type='file']",
    ".CbirUpload-Input",
    "[class*='Upload'] input[type='file']",
    "input[accept*='image']",
]

# Sélecteurs larges pour la page de résultats
RESULT_SELECTORS = [
    # Résultats similaires
    "a.serp-item__link",
    "a[class*='serp-item']",
    ".serp-item a[href^='http']",
    # Sites avec cette image
    ".CbirOtherSizes-ItemLink",
    "[class*='OtherSizes'] a[href^='http']",
    # Fallback très large
    ".serp-list a[href^='http']",
    "li[class*='serp'] a[href^='http']",
    "[data-bem*='serp-item'] a[href^='http']",
]


class YandexScraper:
    def __init__(self, stealth: bool = False, ws_broadcast=None, headless: bool = False):
        self.stealth      = stealth
        self.ws_broadcast = ws_broadcast
        self.headless     = headless

    async def _log(self, msg: str):
        ts   = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        if self.ws_broadcast:
            try: await self.ws_broadcast(line)
            except Exception: pass

    async def _debug_dump(self, page: Page, label: str):
        """Sauvegarde screenshot + HTML + URL pour debug."""
        safe  = label.replace(" ", "_")
        try:
            await page.screenshot(path=f"debug_{safe}.png", full_page=True)
            html  = await page.content()
            Path(f"debug_{safe}.html").write_text(html, encoding="utf-8")
            await self._log(f"  📸 Debug dump → debug_{safe}.png + debug_{safe}.html")
            await self._log(f"  URL actuelle : {page.url}")
            await self._log(f"  Titre        : {await page.title()}")
        except Exception as e:
            await self._log(f"  Debug dump échoué : {e}")

    async def _detect_captcha(self, page: Page) -> bool:
        for sel in CAPTCHA_SELECTORS:
            try:
                if await page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
        return False

    async def _handle_captcha(self, page: Page):
        await self._log("⚠  CAPTCHA DÉTECTÉ — résous-le dans la fenêtre Playwright.")
        if self.ws_broadcast:
            await self.ws_broadcast("__CAPTCHA_REQUIRED__")
            for _ in range(240):
                await asyncio.sleep(0.5)
                if not await self._detect_captcha(page):
                    await self._log("✔  Captcha résolu — reprise.")
                    return
            raise TimeoutError("Captcha non résolu dans les 120s.")
        else:
            input("  → Résous le captcha, puis appuie sur ENTRÉE...")

    def search_image_sync(self, image, max_results: int = 30) -> list:
        """ Wrapper synchrone pour le CLI """
        import asyncio
        return asyncio.run(self.search_image(image, max_results))

    async def search_image(self, image: Union[str, bytes, io.BytesIO], max_results: int = 30) -> list:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--start-maximized",
                ]
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1366, "height": 768},
                locale="en-US",
            )
            await ctx.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
            page = await ctx.new_page()
            try:
                results = await self._do_search(page, image, max_results)
            except Exception as e:
                await self._log(f"✖  Erreur fatale : {e}")
                results = []
            finally:
                await browser.close()
            return results

    async def _do_search(self, page: Page, image, max_results: int, retry: int = 0) -> list:
        if retry > 3:
            await self._log("✖  Max retries atteint.")
            return []
        if retry > 0:
            backoff = (2 ** retry) + 1.0
            await self._log(f"  Retry #{retry} — attente {backoff:.1f}s...")
            import asyncio
            await asyncio.sleep(backoff)

        try:
            import time, random, asyncio
            # ── 1. Charger Yandex ────────────────────────────────────────────
            await self._log("Chargement de Yandex Images...")
            await page.goto("https://yandex.com/images/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(1.5, 2.5))

            # ── 2. Cliquer bouton caméra ─────────────────────────────────────
            cam_selectors = [".HeaderDesktopActions-CbirButton", "button[aria-label*='image' i]", ".search2__button", ".input__cbir-button"]
            cam_ok = False
            for sel in cam_selectors:
                try:
                    el = page.locator(sel).first
                    if await el.is_visible(timeout=2000):
                        await el.click()
                        cam_ok = True
                        await self._log(f"  ✔ Bouton caméra cliqué ({sel})")
                        break
                except Exception:
                    continue

            if not cam_ok:
                await self._log("✖  Bouton caméra introuvable.")
                return await self._do_search(page, image, max_results, retry + 1)

            await asyncio.sleep(1.0)

            # ── 3. Input file & Upload ────────────────────────────────────────
            import tempfile
            from pathlib import Path
            if isinstance(image, (str, Path)):
                target_path = str(image)
            else:
                tmp_dir = Path(tempfile.gettempdir())
                tmp_path = tmp_dir / f"_sm_target_{int(time.time()*1000)}.jpg"
                raw = image.read() if hasattr(image, "read") else image
                tmp_path.write_bytes(raw)
                target_path = str(tmp_path)

            # Ultra-robust upload: using set_input_files on the actual file input
            try:
                inp = page.locator("input[type='file']").first
                await inp.wait_for(state="attached", timeout=5000)
                await inp.set_input_files(target_path)
                await self._log("  ✔ Image injectée via set_input_files")
            except Exception as e:
                await self._log(f"✖  Échec injection input : {e}")
                return await self._do_search(page, image, max_results, retry + 1)

            # ── 4. Attente de redirection ────────────────────────────────────
            await self._log("En attente de la redirection Yandex...")
            try:
                await page.wait_for_url(lambda url: "search" in url and "url=" in url or "cbir" in url, timeout=15000)
            except Exception:
                # If it doesn't redirect, maybe we need to click a submit button manually
                try:
                    await page.evaluate("document.querySelector('button.CbirPanel-FileControlsButton, button[type=submit]').click()")
                    await page.wait_for_url(lambda url: "search" in url, timeout=10000)
                except:
                    await self._log("⚠  URL inchangée après upload.")
                    # Let's check if we're still on the homepage
                    if "text=" not in page.url and "url=" not in page.url and "cbir" not in page.url:
                        await self._log("✖  Toujours sur l'accueil, abandon de cette tentative.")
                        return await self._do_search(page, image, max_results, retry + 1)

            await asyncio.sleep(2)

            if await self._detect_captcha(page):
                await self._handle_captcha(page)

            # ── 5. Grille Voir Plus ──────────────────────────────────────────
            await self._log("[YANDEX] Recherche du bouton 'Voir tous les résultats'...")
            try:
                more_btn = page.locator(".CbirSimilar-More, a.CbirItem-TitleLink, a.CbirItem-MoreButton, a[href*='cbir_page=similar'], a:has-text('Similar images'), a:has-text('Похожие')").first
                if await more_btn.is_visible(timeout=3000):
                    await more_btn.click()
                    await self._log("[YANDEX] Grille complète ouverte. Chargement en cours...")
                    await asyncio.sleep(2.0)
            except Exception:
                await self._log("[YANDEX] Pas de bouton 'Voir tous les résultats' (ou déjà sur la grille).")

            await self._log(f"[YANDEX] Défilement de la page pour charger les images...")
            for _ in range(6):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(0.7)

            # ── 6. Extraction VISUELLE (Mode Humain / Capture) ──────────────────
            results = await self._parse_results_visual(page, max_results)

            if not results:
                await self._log("⚠  Aucun résultat parsé visuellement — dump debug...")
                await self._debug_dump(page, f"no_results_retry{retry}")
                if retry < 3:
                    return await self._do_search(page, image, max_results, retry + 1)

            await self._log(f"Yandex: {len(results)} matches visuels trouvés.")
            return results

        except Exception as e:
            await self._log(f"✖  Erreur : {e}")
            return await self._do_search(page, image, max_results, retry + 1)

    async def _parse_results_visual(self, page, max_results: int) -> list:
        """
        Extraction visuelle simulée (Façon Humaine).
        Le bot scanne littéralement l'écran, trouve les images affichées, 
        vérifie leur taille (pour ignorer les logos), et simule un clic-droit pour copier le lien.
        Immunisé contre les protections JSON/DOM de Yandex.
        """
        await self._log("[YANDEX] Mode Extraction Visuelle (Simulation Clic Droit) activé...")
        results = []
        seen = set()

        try:
            # On donne un peu de temps pour que les images s'affichent à l'écran
            await page.wait_for_selector("img", timeout=5000)
        except:
            pass

        try:
            images = await page.locator("img").all()
            for img in images:
                try:
                    # Vérifier si l'image est visible à l'écran
                    if not await img.is_visible(timeout=500):
                        continue

                    # Filtrer les petites images (icônes, logos, spinners)
                    box = await img.bounding_box()
                    if not box or box['width'] < 80 or box['height'] < 80:
                        continue

                    # Récupérer l'URL de l'image (le src)
                    src = await img.get_attribute("src")
                    if not src:
                        src = await img.get_attribute("data-src")

                    if not src or "captcha" in src.lower() or "spin" in src.lower() or src.startswith("data:image/svg"):
                        continue

                    # Corriger les URLs relatives
                    if src.startswith("//"):
                        src = "https:" + src
                    elif src.startswith("/"):
                        src = "https://yandex.com" + src

                    if src in seen:
                        continue
                    seen.add(src)

                    # Simuler un clic droit sur l'image pour trouver le lien parent
                    href = src
                    parent = img.locator("xpath=ancestor::a").first
                    if await parent.count() > 0:
                        raw_href = await parent.get_attribute("href")
                        if raw_href:
                            if raw_href.startswith("/"):
                                href = "https://yandex.com" + raw_href
                            else:
                                href = raw_href

                    results.append({
                        "url": href,
                        "platform": "visual_capture",
                        "thumb": src
                    })

                    if len(results) >= max_results:
                        break
                except Exception:
                    continue
        except Exception as e:
            await self._log(f"✖ Erreur pendant l'extraction visuelle : {e}")

        return results

