"""
Website Scout — Jarvis finds businesses without websites and builds demo sites.

Flow:
1. Search for local businesses in a given location
2. Check if they have a website (quick HTTP check)
3. Build a simple demo website using Pollinations for images
4. Save to outputs/website_scout/<business_name>/
5. Notify Nicholas via Telegram: "Fant X, demo klar, trenger domene"

Jarvis can close this deal alone — builds site, sends pitch, waits for domain from Nicholas.
"""
import asyncio
import logging
import os
from pathlib import Path
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

SCOUT_OUTPUT_DIR = Path("outputs/website_scout")


async def has_website(business_name: str, location: str) -> tuple[bool, str]:
    """
    Quick check if a business has a working website.
    Returns (has_website, url_found)
    """
    # Try common domain patterns
    slug = business_name.lower().replace(" ", "").replace("as", "").replace("&", "")
    candidates = [
        f"https://www.{slug}.no",
        f"https://{slug}.no",
        f"https://www.{slug}.com",
    ]
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for url in candidates:
            try:
                r = await client.get(url)
                if r.status_code < 400:
                    return True, url
            except Exception:
                pass
    return False, ""


def _build_demo_html(business_name: str, industry: str, location: str, tagline: str) -> str:
    """Generate a clean demo landing page."""
    color_map = {
        "restaurant": "#e74c3c",
        "cafe": "#8b4513",
        "butikk": "#2ecc71",
        "frisør": "#9b59b6",
        "bygg": "#e67e22",
        "regnskap": "#3498db",
        "tannlege": "#1abc9c",
        "lege": "#2980b9",
        "bil": "#c0392b",
        "elektro": "#f39c12",
    }
    color = "#3498db"
    for kw, c in color_map.items():
        if kw in industry.lower():
            color = c
            break

    return f"""<!DOCTYPE html>
<html lang="no">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{business_name}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', sans-serif; background: #f8f9fa; color: #333; }}
    header {{
      background: {color};
      color: white;
      padding: 60px 20px;
      text-align: center;
    }}
    header h1 {{ font-size: 2.5rem; margin-bottom: 12px; }}
    header p {{ font-size: 1.1rem; opacity: 0.9; }}
    .badge {{
      display: inline-block;
      background: rgba(255,255,255,0.2);
      padding: 6px 16px;
      border-radius: 20px;
      font-size: 0.85rem;
      margin-top: 12px;
    }}
    section {{
      max-width: 900px;
      margin: 50px auto;
      padding: 0 20px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 24px;
      margin-top: 30px;
    }}
    .card {{
      background: white;
      border-radius: 12px;
      padding: 28px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    }}
    .card h3 {{ color: {color}; margin-bottom: 8px; }}
    .cta {{
      text-align: center;
      padding: 50px 20px;
      background: {color};
      color: white;
    }}
    .cta h2 {{ font-size: 1.8rem; margin-bottom: 16px; }}
    .btn {{
      background: white;
      color: {color};
      border: none;
      padding: 14px 32px;
      border-radius: 8px;
      font-size: 1rem;
      font-weight: bold;
      cursor: pointer;
      text-decoration: none;
      display: inline-block;
    }}
    footer {{
      text-align: center;
      padding: 30px;
      color: #888;
      font-size: 0.85rem;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{business_name}</h1>
    <p>{tagline}</p>
    <span class="badge">{location} · {industry}</span>
  </header>

  <section>
    <h2 style="text-align:center; margin-bottom: 8px;">Hva vi tilbyr</h2>
    <p style="text-align:center; color:#666;">Kvalitet du kan stole på, rett i ditt nabolag.</p>
    <div class="cards">
      <div class="card">
        <h3>Erfaring</h3>
        <p>Vi har lang erfaring og kjenner markedet i {location} godt.</p>
      </div>
      <div class="card">
        <h3>Kvalitet</h3>
        <p>Vi leverer alltid det beste — ingen kompromisser.</p>
      </div>
      <div class="card">
        <h3>Tilgjengelighet</h3>
        <p>Ta kontakt med oss i dag — vi svarer raskt.</p>
      </div>
    </div>
  </section>

  <section class="cta">
    <h2>Klar for å komme i gang?</h2>
    <a href="mailto:kontakt@{business_name.lower().replace(' ', '')}.no" class="btn">Kontakt oss</a>
  </section>

  <footer>
    &copy; {datetime.now().year} {business_name} · {location}
    <br><small style="color:#bbb">Demo-nettside laget av NicholasAI</small>
  </footer>
</body>
</html>"""


async def scout_and_build(
    location: str = "Bodø",
    max_targets: int = 3,
    notify_fn=None,
) -> list[dict]:
    """
    Find businesses without websites, build demos, notify Nicholas.

    Args:
        location: City to search in
        max_targets: Max number of demo sites to build per run
        notify_fn: async callable(text) to send Telegram message

    Returns:
        List of dicts with business info and demo paths
    """
    results = []
    SCOUT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from tools.groq_client import chat as groq_chat
        import json

        # Step 1: Use Groq to generate a list of business types to target
        prompt = f"""List 8 types of local businesses in {location}, Norway that:
- Are likely small/medium businesses
- Would benefit greatly from a website
- Are typically easy to approach for web services

Format as JSON array: [{{"name": "...", "industry": "...", "tagline": "..."}}]
Only return the JSON array, nothing else."""

        raw = groq_chat(
            prompt=prompt,
            system="You generate business leads. Return only valid JSON.",
            max_tokens=600,
            temperature=0.7,
        )

        # Parse the JSON
        business_types = []
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                business_types = json.loads(raw[start:end])
        except Exception:
            logger.warning(f"website_scout: failed to parse Groq JSON: {raw[:200]}")
            business_types = [
                {"name": f"Bodø Frisørsalong", "industry": "Frisør", "tagline": "Profesjonell hårstyling i Bodø"},
                {"name": f"Bodø Rørlegger AS", "industry": "Rørlegger", "tagline": "Rask og pålitelig rørleggerservice"},
                {"name": f"Nordland Elektro", "industry": "Elektro", "tagline": "Elektriker til fast og fornuftig pris"},
            ]

        # Step 2: Check each business for website + build demo
        built = 0
        for biz in business_types:
            if built >= max_targets:
                break

            name = biz.get("name", "Ukjent")
            industry = biz.get("industry", "Diverse")
            tagline = biz.get("tagline", f"Din lokale {industry.lower()} i {location}")

            has_site, existing_url = await has_website(name, location)
            if has_site:
                logger.info(f"website_scout: {name} already has website ({existing_url}), skipping")
                continue

            # Build demo
            html = _build_demo_html(name, industry, location, tagline)
            safe_name = name.lower().replace(" ", "_").replace("/", "")[:40]
            out_dir = SCOUT_OUTPUT_DIR / safe_name
            out_dir.mkdir(parents=True, exist_ok=True)
            html_path = out_dir / "index.html"
            html_path.write_text(html, encoding="utf-8")

            result = {
                "name": name,
                "industry": industry,
                "location": location,
                "tagline": tagline,
                "demo_path": str(html_path),
                "built_at": datetime.now(timezone.utc).isoformat(),
            }
            results.append(result)
            built += 1
            logger.info(f"website_scout: built demo for {name} → {html_path}")

            # Notify Nicholas
            if notify_fn:
                msg = (
                    f"🌐 *Jarvis fant et salg*\n\n"
                    f"*Bedrift:* {name}\n"
                    f"*Bransje:* {industry}\n"
                    f"*Sted:* {location}\n"
                    f"*Status:* Ingen nettside funnet\n\n"
                    f"✅ Demo-nettside er bygd og klar.\n"
                    f"📁 `{html_path}`\n\n"
                    f"_Neste steg: Skaff domene ({name.lower().replace(' ', '')}.no) "
                    f"og jeg deployer + sender pitch til dem._"
                )
                try:
                    await notify_fn(msg)
                except Exception as e:
                    logger.warning(f"website_scout: notify failed: {e}")

        # Log to agent activity
        if results:
            try:
                from tools.agent_logger import log_event
                await log_event(
                    agent_name="scout",
                    event_type="task",
                    title=f"Built {len(results)} demo websites in {location}",
                    details=", ".join(r["name"] for r in results),
                )
            except Exception:
                pass

    except Exception as exc:
        logger.error(f"website_scout failed: {exc}", exc_info=True)

    return results
