"""
core/multi_engine.py  —  Moteurs de recherche visuelle alternatifs
Ordre de repli : Yandex -> Google Lens -> Bing Visual Search
Active si resultats Yandex < MIN_RESULTS (defaut : 3)
"""

import asyncio, time, io, random, json
from pathlib import Path
from typing import Union
from playwright.async_api import Page, TimeoutError as PWTimeout

MIN_RESULTS = -1   # seuil de repli

PLATFORM_MAP = {
    "instagram.com": "instagram", "facebook.com": "facebook",
    "vk.com":        "vk",        "twitter.com":  "twitter",
    "x.com":         "twitter",   "linkedin.com": "linkedin",
    "tiktok.com":    "tiktok",    "pinterest.com": "pinterest",
}
SKIP_DOMAINS = [
    "google.", "gstatic.", "bing.com", "microsoft.", "yandex.",
    "javascript:", "about:", "mailto:",
]


def _classify(href: str) -> str:
    return next((v for k, v in PLATFORM_MAP.items() if k in href), "web")


def _skip(href: str) -> bool:
    return any(s in href for s in SKIP_DOMAINS)


async def _js_links(page: Page, max_results: int) -> list:
    """Extrait tous les liens externes via JS evaluate (instantane)."""
    try:
        raw = await page.evaluate(
            f"""
            () => {{
                const r = [];
                const seen = new Set();
                for (const a of document.querySelectorAll("a[href]")) {{
                    const h = a.href || "";
                    if (!h.startsWith("http") || seen.has(h)) continue;
                    seen.add(h);
                    const img = a.querySelector("img");
                    r.push({{ href: h, thumb: img ? img.src : null }});
                    if (r.length >= {max_results * 3}) break;
                }}
                return r;
            }}
        """
        )
        results = []
        for item in raw:
            href = item.get("href", "")
            if _skip(href):
                continue
            results.append({
                "url":      href,
                "platform": _classify(href),
                "thumb":    item.get("thumb"),
            })
            if len(results) >= max_results:
                break
        return results
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE LENS
# ─────────────────────────────────────────────────────────────────────────────
async def google_lens_search(
    page: Page,
    image: Union[str, bytes, io.BytesIO],
    log_fn,
    max_results: int = 30,
) -> list:
    """Recherche Google Lens via Playwright (upload fichier)."""
    import tempfile
    ts = lambda: time.strftime("%H:%M:%S")

    try:
        await log_fn(f"[{ts()}] [LENS] Chargement Google Lens...")
        await page.goto("https://lens.google.com/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # Bouton "Rechercher par image" / camera
        cam_selectors = [
            "button[aria-label*='Search by image' i]",
            "button[aria-label*='image' i]",
            "[data-ved] button",
            ".nDcEnd",
            "div[role='button'][aria-label*='Lens']",
        ]
        for sel in cam_selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=5000)
                await el.click()
                await log_fn(f"[{ts()}] [LENS] Camera cliquee ({sel})")
                break
            except Exception:
                continue

        await asyncio.sleep(0.8)

        # Onglet Upload
        for sel in ["button[aria-label*='Upload' i]", "button:has-text('Upload')",
                    "button:has-text('Importer')", "[data-tabid='upload']"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=3000)
                await el.click()
                break
            except Exception:
                continue

        # Input file
        file_input = None
        for sel in ["input[type='file']", "input[accept*='image']"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="attached", timeout=5000)
                file_input = el
                break
            except Exception:
                continue

        if file_input is None:
            await log_fn(f"[{ts()}] [LENS] Input file introuvable")
            return []

        # Upload
        tmp_path = None
        try:
            if isinstance(image, (str, Path)):
                await file_input.set_input_files(str(image))
            else:
                tmp_dir  = Path(tempfile.gettempdir())
                tmp_path = tmp_dir / f"_sm_lens_{int(time.time()*1000)}.jpg"
                raw      = image.read() if hasattr(image, "read") else image
                tmp_path.write_bytes(raw)
                await file_input.set_input_files(str(tmp_path))
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        await log_fn(f"[{ts()}] [LENS] Upload envoye — attente resultats...")

        # Attente changement URL
        try:
            await page.wait_for_url(
                lambda u: "lens.google.com/search" in u or "google.com/search" in u,
                timeout=20000
            )
        except PWTimeout:
            pass
        await asyncio.sleep(2)

        results = await _js_links(page, max_results)
        await log_fn(f"[{ts()}] [LENS] {len(results)} resultats Google Lens")
        return results

    except Exception as e:
        await log_fn(f"[{ts()}] [LENS] Erreur : {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# BING VISUAL SEARCH
# ─────────────────────────────────────────────────────────────────────────────
async def bing_visual_search(
    page: Page,
    image: Union[str, bytes, io.BytesIO],
    log_fn,
    max_results: int = 30,
) -> list:
    """Recherche Bing Visual Search via Playwright."""
    import tempfile
    ts = lambda: time.strftime("%H:%M:%S")

    try:
        await log_fn(f"[{ts()}] [BING] Chargement Bing Images...")
        await page.goto("https://www.bing.com/images", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(random.uniform(1.5, 2.5))

        # Bouton camera Bing
        cam_selectors = [
            "#sbiBtn",
            "a[aria-label*='Search using an image' i]",
            "label[for='sbi_fileUpload']",
            "button[aria-label*='Visual' i]",
            ".search-box .icon-camera",
        ]
        for sel in cam_selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="visible", timeout=5000)
                await el.click()
                await log_fn(f"[{ts()}] [BING] Camera cliquee ({sel})")
                break
            except Exception:
                continue

        await asyncio.sleep(0.8)

        # Input file
        file_input = None
        for sel in ["input[type='file']", "#sbi_fileUpload", "input[accept*='image']"]:
            try:
                el = page.locator(sel).first
                await el.wait_for(state="attached", timeout=5000)
                file_input = el
                break
            except Exception:
                continue

        if file_input is None:
            await log_fn(f"[{ts()}] [BING] Input file introuvable")
            return []

        tmp_path = None
        try:
            if isinstance(image, (str, Path)):
                await file_input.set_input_files(str(image))
            else:
                tmp_dir  = Path(tempfile.gettempdir())
                tmp_path = tmp_dir / f"_sm_bing_{int(time.time()*1000)}.jpg"
                raw      = image.read() if hasattr(image, "read") else image
                tmp_path.write_bytes(raw)
                await file_input.set_input_files(str(tmp_path))
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        await log_fn(f"[{ts()}] [BING] Upload envoye — attente resultats...")

        try:
            await page.wait_for_url(
                lambda u: "bing.com/images/search" in u or "visualsearch" in u,
                timeout=20000
            )
        except PWTimeout:
            pass
        await asyncio.sleep(2)

        results = await _js_links(page, max_results)
        await log_fn(f"[{ts()}] [BING] {len(results)} resultats Bing Visual")
        return results

    except Exception as e:
        await log_fn(f"[{ts()}] [BING] Erreur : {e}")
        return []
