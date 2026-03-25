"""
URL-leser — henter og renser innhold fra nettsider og GitHub.

Spesialstøtte for:
- GitHub repos (README + beskrivelse via GitHub API)
- GitHub profiler (hvem er personen, hva bygger de)
- Generelle nettsider (BeautifulSoup eller urllib fallback)
- Reddit-tråder
- Artikler / nyheter

Brukes av bot.py når en melding inneholder en URL.
"""
import json
import logging
import os
import re
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "Accept-Language": "no,en;q=0.9",
}


# ── Offentlig API ──────────────────────────────────────────────────────────────

def extract_urls(text: str) -> list[str]:
    """Finn alle URLs i en tekst."""
    return re.findall(r'https?://[^\s\)\]\>\"\']+', text)


def read_url(url: str, max_chars: int = 4000) -> str:
    """
    Les en URL og returner renset tekst.
    Velger beste metode basert på domenet.
    """
    url = url.rstrip(".,;)")  # Rens vanlige avslutningspunkter
    logger.info(f"Leser URL: {url}")

    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()

        if "github.com" in domain:
            return _read_github(url, max_chars)
        elif "reddit.com" in domain:
            return _read_reddit(url, max_chars)
        else:
            return _read_generic(url, max_chars)
    except Exception as e:
        logger.error(f"URL-lesing feilet for {url}: {e}")
        return f"Kunne ikke lese {url}: {e}"


def read_urls_in_text(text: str, max_chars_per_url: int = 3000) -> list[tuple[str, str]]:
    """
    Finn og les alle URLer i en tekst.
    Returnerer liste av (url, innhold) tupler.
    """
    urls = extract_urls(text)
    results = []
    for url in urls[:3]:  # Maks 3 URLer per melding
        content = read_url(url, max_chars_per_url)
        results.append((url, content))
    return results


# ── GitHub ─────────────────────────────────────────────────────────────────────

def _read_github(url: str, max_chars: int) -> str:
    """Les GitHub-lenker via GitHub API (ingen token nødvendig for offentlige repos)."""
    parsed = urllib.parse.urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]

    if not parts:
        return _read_generic(url, max_chars)

    # GitHub profil: github.com/username
    if len(parts) == 1:
        return _github_profile(parts[0], max_chars)

    # GitHub repo: github.com/username/repo
    if len(parts) >= 2:
        owner, repo = parts[0], parts[1]
        # Sjekk om det er en spesifikk fil
        if len(parts) > 2 and parts[2] in ("blob", "tree"):
            return _github_file(owner, repo, "/".join(parts[4:]) if len(parts) > 4 else "", max_chars)
        return _github_repo(owner, repo, max_chars)

    return _read_generic(url, max_chars)


def _github_api(path: str) -> dict:
    """Gjør GitHub API-kall."""
    token = os.getenv("GITHUB_TOKEN", "")
    headers_gh = {"Accept": "application/vnd.github.v3+json", "User-Agent": "NexusBot/1.0"}
    if token:
        headers_gh["Authorization"] = f"token {token}"

    req = urllib.request.Request(f"https://api.github.com{path}", headers=headers_gh)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _github_profile(username: str, max_chars: int) -> str:
    """Les GitHub-profil."""
    try:
        user = _github_api(f"/users/{username}")
        repos_data = _github_api(f"/users/{username}/repos?sort=stars&per_page=6")

        lines = [
            f"**GitHub-profil: {user.get('name') or username}** (@{username})",
            f"Bio: {user.get('bio') or 'Ingen bio'}",
            f"Lokasjon: {user.get('location') or 'Ukjent'}",
            f"Følgere: {user.get('followers', 0)} | Følger: {user.get('following', 0)}",
            f"Offentlige repos: {user.get('public_repos', 0)}",
            f"Firma: {user.get('company') or 'Ingen'}",
            "",
            "**Topp repos:**",
        ]
        for r in repos_data[:6]:
            stars = r.get("stargazers_count", 0)
            desc = r.get("description") or "Ingen beskrivelse"
            lang = r.get("language") or ""
            lines.append(f"• {r['name']} ⭐{stars} [{lang}] — {desc[:100]}")

        return "\n".join(lines)[:max_chars]
    except Exception as e:
        logger.warning(f"GitHub profil API feilet, prøver HTML: {e}")
        return _read_generic(f"https://github.com/{username}", max_chars)


def _github_repo(owner: str, repo: str, max_chars: int) -> str:
    """Les GitHub-repo: info + README."""
    try:
        data = _github_api(f"/repos/{owner}/{repo}")
        lines = [
            f"**GitHub Repo: {owner}/{repo}**",
            f"Beskrivelse: {data.get('description') or 'Ingen beskrivelse'}",
            f"Språk: {data.get('language') or 'Ukjent'}",
            f"Stjerner: {data.get('stargazers_count', 0)} | Forks: {data.get('forks_count', 0)}",
            f"Lisens: {(data.get('license') or {}).get('name', 'Ingen')}",
            f"Oppdatert: {data.get('updated_at', '')[:10]}",
            f"URL: https://github.com/{owner}/{repo}",
            "",
        ]

        # Hent README
        try:
            readme = _github_api(f"/repos/{owner}/{repo}/readme")
            import base64
            readme_text = base64.b64decode(readme["content"]).decode("utf-8", errors="ignore")
            # Rens markdown litt
            readme_text = re.sub(r"!\[.*?\]\(.*?\)", "", readme_text)  # Fjern bilder
            readme_text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", readme_text)  # Flatten lenker
            lines.append("**README:**")
            lines.append(readme_text[:2000])
        except Exception:
            lines.append("(README ikke tilgjengelig)")

        return "\n".join(lines)[:max_chars]
    except Exception as e:
        logger.warning(f"GitHub repo API feilet, prøver HTML: {e}")
        return _read_generic(f"https://github.com/{owner}/{repo}", max_chars)


def _github_file(owner: str, repo: str, filepath: str, max_chars: int) -> str:
    """Les en spesifikk fil fra GitHub."""
    try:
        data = _github_api(f"/repos/{owner}/{repo}/contents/{filepath}")
        import base64
        content = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
        return f"**Fil: {filepath}** ({owner}/{repo})\n\n{content[:max_chars]}"
    except Exception as e:
        return f"Kunne ikke lese filen: {e}"


# ── Reddit ─────────────────────────────────────────────────────────────────────

def _read_reddit(url: str, max_chars: int) -> str:
    """Les Reddit-tråd via JSON API."""
    try:
        # Reddit har JSON API: legg til .json på slutten
        json_url = url.rstrip("/") + ".json?limit=10"
        req = urllib.request.Request(json_url, headers={"User-Agent": "NexusBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        post = data[0]["data"]["children"][0]["data"]
        lines = [
            f"**Reddit: {post.get('title', '')}**",
            f"Subreddit: r/{post.get('subreddit', '')}",
            f"Score: {post.get('score', 0)} | Kommentarer: {post.get('num_comments', 0)}",
            f"Tekst: {(post.get('selftext') or '')[:500]}",
            "",
            "**Topp kommentarer:**",
        ]

        comments = data[1]["data"]["children"]
        for c in comments[:5]:
            cd = c.get("data", {})
            body = cd.get("body", "")
            score = cd.get("score", 0)
            if body and body != "[deleted]":
                lines.append(f"• (↑{score}) {body[:200]}")

        return "\n".join(lines)[:max_chars]
    except Exception as e:
        logger.warning(f"Reddit JSON API feilet: {e}")
        return _read_generic(url, max_chars)


# ── Generisk nettside ──────────────────────────────────────────────────────────

def _read_generic(url: str, max_chars: int) -> str:
    """Generisk URL-leser — prøver BeautifulSoup, faller tilbake til urllib."""
    try:
        return _read_with_bs4(url, max_chars)
    except ImportError:
        return _read_with_urllib(url, max_chars)
    except Exception as e:
        logger.warning(f"BS4 feilet, prøver urllib: {e}")
        return _read_with_urllib(url, max_chars)


def _read_with_bs4(url: str, max_chars: int) -> str:
    """Les URL med BeautifulSoup."""
    import httpx
    from bs4 import BeautifulSoup

    with httpx.Client(timeout=12, follow_redirects=True, headers=HEADERS) as client:
        resp = client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    title = soup.title.string.strip() if soup.title else url

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    # Prioriter artikkel/main-innhold
    main = soup.find("article") or soup.find("main") or soup.find(id="content") or soup.body
    text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)

    # Rens whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)

    return f"**{title}**\nURL: {url}\n\n{text[:max_chars]}"


def _read_with_urllib(url: str, max_chars: int) -> str:
    """Les URL kun med urllib (ingen ekstra avhengigheter)."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")

    # Fjern HTML-tags med regex
    text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&[a-z]+;", "", text)
    text = re.sub(r"\s{3,}", "\n\n", text)

    # Finn tittel
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else url

    return f"**{title}**\nURL: {url}\n\n{text[:max_chars]}"
