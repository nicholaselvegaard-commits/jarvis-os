"""
NEXUS Browser — Playwright nettleserautomatisering.

Lar NEXUS faktisk gjøre ting på nett — ikke bare lese.
Bruker Playwright headless Chromium.

Installer: pip install playwright && playwright install chromium
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def browse(url: str, task: str = "read", selector: Optional[str] = None) -> str:
    """
    Naviger til URL og utfør oppgave.

    Args:
        url:      Nettadressen
        task:     "read" | "screenshot" | "links" | "search:[query]"
        selector: CSS-selector å fokusere på (valgfritt)

    Returns:
        Tekstlig resultat av handlingen.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "Playwright ikke installert. Kjør: pip install playwright && playwright install chromium"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")

            result = ""

            if task == "read":
                if selector:
                    try:
                        el = await page.query_selector(selector)
                        result = await el.inner_text() if el else ""
                    except Exception:
                        pass
                if not result:
                    result = await page.inner_text("body")
                result = _clean(result)[:4000]

            elif task == "links":
                anchors = await page.query_selector_all("a[href]")
                links = []
                for a in anchors[:50]:
                    href = await a.get_attribute("href")
                    text = (await a.inner_text()).strip()
                    if href and text:
                        links.append(f"{text}: {href}")
                result = "\n".join(links[:30])

            elif task == "screenshot":
                path = "/tmp/nexus_screenshot.png"
                await page.screenshot(path=path, full_page=False)
                result = f"Skjermbilde lagret: {path}"

            elif task.startswith("search:"):
                query = task[7:].strip()
                try:
                    await page.fill('input[type="search"], input[name="q"], input[type="text"]', query)
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("domcontentloaded", timeout=8000)
                    result = _clean(await page.inner_text("body"))[:3000]
                except Exception as e:
                    result = f"Søk feilet: {e}"

            elif task == "title":
                result = await page.title()

            else:
                result = _clean(await page.inner_text("body"))[:3000]

            await browser.close()
            return result or "(tom side)"

    except Exception as e:
        logger.error(f"browser.browse feil ({url}): {e}")
        return f"Nettleserfeil: {e}"


def browse_sync(url: str, task: str = "read", selector: Optional[str] = None) -> str:
    """Synkron wrapper for ikke-async kontekster."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, browse(url, task, selector))
                return future.result(timeout=30)
        else:
            return loop.run_until_complete(browse(url, task, selector))
    except Exception as e:
        return f"Feil: {e}"


def google_search(query: str, num: int = 5) -> str:
    """Søk Google og returnerer toppresultater."""
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=no"
    raw = browse_sync(url, task="read", selector="#search")
    if not raw or "Nettleserfeil" in raw:
        return raw
    lines = [l.strip() for l in raw.splitlines() if len(l.strip()) > 30]
    return "\n".join(lines[:40])


def _clean(text: str) -> str:
    """Rens tekst — fjern tomme linjer og overflødig whitespace."""
    import re
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()
