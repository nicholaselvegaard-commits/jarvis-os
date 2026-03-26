"""
Jarvis Browser Agent — autonom nettleser med LLM-styring.

Kan:
- Navigere og lese nettsider
- Opprette kontoer automatisk
- Håndtere email-verifisering via IMAP
- Fylle ut skjemaer
- Scrape data

Bruk:
    agent = BrowserAgent()
    result = await agent.task("Gå til proff.no og finn kontaktinfo for AIDN AS")
    result = await agent.create_account("twitter.com", {"email": "...", "password": "..."})
"""

import asyncio
import base64
import json
import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/opt/nexus/.env")

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"

# Anti-detection config
STEALTH = {
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    ],
    "viewport": {"width": 1920, "height": 1080},
    "locale": "nb-NO",
    "timezone": "Europe/Oslo",
    "typing_wpm": (80, 120),
    "action_delay": (0.5, 2.0),
}


class BrowserAgent:
    def __init__(self):
        self.browser = None
        self.page = None
        self.context = None
        self._client = None
        self.history = []  # action log

    @property
    def client(self):
        if not self._client:
            import anthropic
            self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        return self._client

    async def start(self):
        """Start headless browser."""
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        self.context = await self.browser.new_context(
            user_agent=random.choice(STEALTH["user_agents"]),
            viewport=STEALTH["viewport"],
            locale=STEALTH["locale"],
            timezone_id=STEALTH["timezone"],
        )
        # Skjul playwright-fingerprint
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['nb-NO', 'nb', 'no', 'en-US', 'en']});
        """)
        self.page = await self.context.new_page()
        logger.info("Browser startet")

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if hasattr(self, '_pw'):
            await self._pw.stop()

    async def screenshot_b64(self) -> str:
        """Ta screenshot og returner som base64."""
        data = await self.page.screenshot(type="jpeg", quality=75, full_page=False)
        return base64.b64encode(data).decode()

    async def _delay(self):
        """Human-like forsinkelse mellom handlinger."""
        d = random.uniform(*STEALTH["action_delay"])
        await asyncio.sleep(d)

    async def _type_human(self, selector: str, text: str):
        """Skriv tekst med menneskelig hastighet."""
        await self.page.click(selector)
        wpm = random.randint(*STEALTH["typing_wpm"])
        delay_per_char = 60 / (wpm * 5)  # sekunder per tegn
        for char in text:
            await self.page.keyboard.type(char)
            await asyncio.sleep(delay_per_char + random.uniform(0, 0.05))

    async def _ask_llm(self, screenshot_b64: str, task: str, history_summary: str) -> dict:
        """
        Spør Claude hva neste handling skal være.
        Returnerer: {"action": str, "params": dict, "reasoning": str, "done": bool}
        """
        system = """Du er et browser automation system. Analyser screenshot og bestem neste handling.

Svar ALLTID med valid JSON i dette formatet:
{
  "reasoning": "kort forklaring av hva du ser og hva som er neste steg",
  "action": "navigate|click|type|scroll|wait|done|fail",
  "params": {
    "url": "...",          // for navigate
    "selector": "...",    // CSS selector for click/type
    "text": "...",        // for type
    "direction": "down",  // for scroll
    "reason": "..."       // for done/fail
  },
  "done": false
}

Actions:
- navigate: gå til URL
- click: klikk på element (bruk CSS selector eller text='...' format)
- type: skriv tekst i element
- scroll: scroll siden
- wait: vent (params.ms = millisekunder)
- done: oppgaven er fullført
- fail: umulig å fullføre, forklar hvorfor"""

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": screenshot_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"OPPGAVE: {task}\n\nHISTORIKK: {history_summary}\n\nHva er neste handling?",
                    },
                ],
            }
        ]

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system,
            messages=messages,
        )

        text = response.content[0].text
        # Trekk ut JSON fra responsen
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return {"action": "fail", "params": {"reason": "LLM returnerte ikke JSON"}, "done": True}
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return {"action": "fail", "params": {"reason": "JSON parse feil"}, "done": True}

    async def _execute_action(self, action: dict) -> str:
        """Utfør en handling og returner status."""
        name = action.get("action", "")
        params = action.get("params", {})

        try:
            if name == "navigate":
                url = params.get("url", "")
                if not url.startswith("http"):
                    url = "https://" + url
                await self.page.goto(url, wait_until="networkidle", timeout=15000)
                return f"Navigerte til {url}"

            elif name == "click":
                sel = params.get("selector", "")
                if sel.startswith("text="):
                    text = sel[5:]
                    await self.page.get_by_text(text, exact=False).first.click()
                else:
                    await self.page.click(sel, timeout=5000)
                await self._delay()
                return f"Klikket: {sel}"

            elif name == "type":
                sel = params.get("selector", "")
                text = params.get("text", "")
                await self._type_human(sel, text)
                await self._delay()
                return f"Skrev: {text[:30]}..."

            elif name == "scroll":
                direction = params.get("direction", "down")
                delta = 600 if direction == "down" else -600
                await self.page.mouse.wheel(0, delta)
                await asyncio.sleep(0.5)
                return "Scrollet"

            elif name == "wait":
                ms = params.get("ms", 2000)
                await asyncio.sleep(ms / 1000)
                return f"Ventet {ms}ms"

            elif name == "done":
                return "DONE: " + params.get("reason", "Fullført")

            elif name == "fail":
                return "FAIL: " + params.get("reason", "Ukjent feil")

            else:
                return f"Ukjent action: {name}"

        except Exception as e:
            return f"Feil ved {name}: {e}"

    async def task(self, objective: str, max_steps: int = 20) -> dict:
        """
        Kjør en nettleseroppgave med LLM-styring.

        Args:
            objective: Hva som skal gjøres
            max_steps: Maks antall handlinger

        Returns:
            {"success": bool, "result": str, "steps": int, "history": list}
        """
        if not self.page:
            await self.start()

        logger.info(f"Browser task: {objective}")
        self.history = []

        for step in range(max_steps):
            screenshot = await self.screenshot_b64()
            history_text = " → ".join([h["action"] for h in self.history[-5:]]) or "start"

            action = await self._ask_llm(screenshot, objective, history_text)
            self.history.append({
                "step": step + 1,
                "action": action.get("action"),
                "params": action.get("params", {}),
                "reasoning": action.get("reasoning", ""),
            })

            result = await self._execute_action(action)
            logger.info(f"  Step {step+1}: {action.get('action')} → {result[:80]}")

            if action.get("action") in ("done", "fail") or action.get("done"):
                success = action.get("action") == "done"
                return {
                    "success": success,
                    "result": result,
                    "steps": step + 1,
                    "history": self.history,
                    "url": self.page.url,
                }

            await self._delay()

        return {
            "success": False,
            "result": f"Maks {max_steps} steg nådd uten fullføring",
            "steps": max_steps,
            "history": self.history,
        }

    async def read_page(self, url: str) -> dict:
        """Naviger til URL og returner tekst + tittel."""
        if not self.page:
            await self.start()
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = await self.page.title()
        text = await self.page.evaluate("() => document.body.innerText")
        return {
            "url": url,
            "title": title,
            "text": text[:5000],
        }

    async def create_account(self, website: str, credentials: dict) -> dict:
        """
        Opprett konto på et nettsted autonomt.

        Args:
            website: URL til nettstedet
            credentials: {"email": "...", "password": "...", "name": "...", ...}

        Returns:
            {"success": bool, "result": str, "account": dict}
        """
        cred_desc = ", ".join(f"{k}={'***' if 'pass' in k else v}" for k, v in credentials.items())
        objective = (
            f"Opprett en ny konto på {website}. "
            f"Bruk disse opplysningene: {cred_desc}. "
            f"Finn signup/registrer-knappen, fyll ut skjemaet, og fullfør registreringen. "
            f"Hvis det er email-verifisering, si fra."
        )
        result = await self.task(objective)
        if result["success"]:
            # Logg konto i brain
            try:
                import sys
                sys.path.insert(0, "/opt/nexus")
                from memory.brain import Brain
                b = Brain()
                b.remember(
                    f"Konto opprettet på {website}: {credentials.get('email', '')}",
                    category="task",
                    tags=["konto", website.split(".")[0]],
                )
            except Exception:
                pass
        return {**result, "account": credentials, "website": website}

    async def handle_email_verification(self, email: str, timeout_sec: int = 60) -> str:
        """
        Vent på og håndter email-verifisering via IMAP.

        Returns:
            Verifiserings-URL eller tom streng
        """
        import imaplib
        import email as email_lib

        imap_host = os.getenv("IMAP_HOST", "")
        imap_user = os.getenv("IMAP_USER", email)
        imap_pass = os.getenv("IMAP_PASSWORD", "")

        if not imap_host or not imap_pass:
            return ""

        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                mail = imaplib.IMAP4_SSL(imap_host)
                mail.login(imap_user, imap_pass)
                mail.select("inbox")
                _, msgs = mail.search(None, "UNSEEN")
                for num in msgs[0].split()[-5:]:
                    _, data = mail.fetch(num, "(RFC822)")
                    msg = email_lib.message_from_bytes(data[0][1])
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/html":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors="ignore")
                    urls = re.findall(r'https?://[^\s"\'<>]+verif[^\s"\'<>]+', body, re.IGNORECASE)
                    if urls:
                        mail.close()
                        mail.logout()
                        # Klikk verifiserings-link
                        await self.page.goto(urls[0], wait_until="networkidle", timeout=15000)
                        return urls[0]
                mail.close()
                mail.logout()
            except Exception as e:
                logger.warning(f"IMAP feil: {e}")
            await asyncio.sleep(5)

        return ""

    async def scrape(self, url: str, data_description: str) -> dict:
        """
        Skrap spesifikk data fra en nettside via LLM-analyse.
        """
        page_data = await self.read_page(url)
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"Ekstraher dette fra nettsiden: {data_description}\n\nNETTSIDE INNHOLD:\n{page_data['text'][:4000]}",
            }],
        )
        return {
            "url": url,
            "extracted": response.content[0].text,
            "source_title": page_data["title"],
        }


# ── Sync wrapper for bruk fra workers ─────────────────────────────────────────

def run_browser_task(task: str, url: str = None) -> dict:
    """Synkron wrapper — bruk fra workers og Telegram bot."""
    async def _run():
        agent = BrowserAgent()
        try:
            if url:
                await agent.start()
                result = await agent.task(f"Naviger til {url}. Deretter: {task}")
            else:
                await agent.start()
                result = await agent.task(task)
            return result
        finally:
            await agent.stop()
    return asyncio.run(_run())


def scrape_url(url: str, what: str) -> str:
    """Enkel scrape — returner ekstrahert tekst."""
    async def _run():
        agent = BrowserAgent()
        try:
            await agent.start()
            result = await agent.scrape(url, what)
            return result["extracted"]
        finally:
            await agent.stop()
    return asyncio.run(_run())
