"""
NEXUS Agent Dashboard — Privat web-plattform for Nicholas.

Tilgang: http://89.167.100.7:8090
Passord: satt i .env som DASHBOARD_PASSWORD

Funksjoner:
- Post oppgaver til agenter (NEXUS, Jordan)
- Se alle aktive og fullførte oppgaver
- Live statusfeed fra MCP-board
- Trigger NEXUS-kjøringer manuelt
"""

import os
from datetime import datetime
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="NEXUS Dashboard", docs_url=None, redoc_url=None)
security = HTTPBasic()

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "nexus2026")
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "nicholas")


def verify(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode(), DASHBOARD_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), DASHBOARD_PASSWORD.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return credentials.username


HTML_BASE = """<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEXUS — Agent Platform</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0a0a0f; color: #e0e0e0; font-family: 'Courier New', monospace; min-height: 100vh; }}
  .header {{ background: #0d0d1a; border-bottom: 1px solid #1a1a3e; padding: 16px 32px; display: flex; align-items: center; gap: 16px; }}
  .logo {{ color: #7c3aed; font-size: 22px; font-weight: bold; letter-spacing: 3px; }}
  .status-dot {{ width: 10px; height: 10px; background: #22c55e; border-radius: 50%; animation: pulse 2s infinite; }}
  @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }}
  .card {{ background: #0d0d1a; border: 1px solid #1a1a3e; border-radius: 12px; padding: 20px; }}
  .card h2 {{ color: #7c3aed; font-size: 13px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 16px; }}
  .stat {{ font-size: 36px; font-weight: bold; color: #fff; }}
  .stat-label {{ color: #666; font-size: 12px; margin-top: 4px; }}
  .task-form {{ background: #0d0d1a; border: 1px solid #1a1a3e; border-radius: 12px; padding: 24px; margin-bottom: 32px; }}
  .task-form h2 {{ color: #7c3aed; font-size: 13px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 16px; }}
  .form-row {{ display: grid; grid-template-columns: 1fr 200px 160px; gap: 12px; align-items: end; }}
  input, select, textarea {{ background: #111122; border: 1px solid #2a2a4e; color: #e0e0e0; padding: 10px 14px; border-radius: 8px; font-family: inherit; font-size: 14px; width: 100%; }}
  textarea {{ resize: vertical; min-height: 80px; }}
  button {{ background: #7c3aed; color: #fff; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-family: inherit; font-size: 14px; font-weight: bold; letter-spacing: 1px; white-space: nowrap; }}
  button:hover {{ background: #6d28d9; }}
  button.secondary {{ background: #1a1a3e; }}
  button.secondary:hover {{ background: #2a2a5e; }}
  .feed {{ background: #0d0d1a; border: 1px solid #1a1a3e; border-radius: 12px; padding: 24px; }}
  .feed h2 {{ color: #7c3aed; font-size: 13px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 16px; }}
  .entry {{ border-bottom: 1px solid #111122; padding: 12px 0; }}
  .entry:last-child {{ border-bottom: none; }}
  .entry-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; letter-spacing: 1px; }}
  .badge-task {{ background: #1e3a5f; color: #60a5fa; }}
  .badge-signal {{ background: #3f1d1d; color: #f87171; }}
  .badge-insight {{ background: #1a3329; color: #4ade80; }}
  .badge-message {{ background: #2a1f3d; color: #a78bfa; }}
  .entry-source {{ color: #666; font-size: 12px; }}
  .entry-title {{ font-weight: bold; color: #fff; font-size: 14px; }}
  .entry-content {{ color: #888; font-size: 13px; line-height: 1.5; margin-top: 4px; }}
  .entry-time {{ color: #444; font-size: 11px; margin-left: auto; }}
  .actions-bar {{ display: flex; gap: 12px; margin-bottom: 32px; flex-wrap: wrap; }}
  .success-msg {{ background: #1a3329; border: 1px solid #166534; color: #4ade80; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }}
  .quick-tasks {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; margin-top: 12px; }}
  .quick-btn {{ background: #111122; border: 1px solid #2a2a4e; color: #a78bfa; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 12px; text-align: left; }}
  .quick-btn:hover {{ background: #1a1a3e; border-color: #7c3aed; }}
  @media (max-width: 700px) {{ .grid {{ grid-template-columns: 1fr; }} .form-row {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="header">
  <div class="logo">⬡ NEXUS</div>
  <div class="status-dot"></div>
  <span style="color:#666;font-size:13px;">Agent Platform — {time}</span>
</div>
<div class="container">
  {content}
</div>
<script>
// Auto-refresh feed hvert 30 sek
setTimeout(() => location.reload(), 30000);
// Quick task buttons
document.querySelectorAll('.quick-btn').forEach(btn => {{
  btn.onclick = () => {{
    document.getElementById('task-input').value = btn.textContent.trim();
    document.getElementById('task-input').focus();
  }};
}});
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: str = Depends(verify), msg: str = ""):
    from tools.mcp_board import board

    entries = board.read(limit=20)
    stats = {
        "total": len(entries),
        "tasks": sum(1 for e in entries if e.get("type") == "task"),
        "signals": sum(1 for e in entries if e.get("type") == "signal"),
        "insights": sum(1 for e in entries if e.get("type") == "insight"),
    }

    def badge(t):
        return f'<span class="badge badge-{t}">{t.upper()}</span>'

    feed_html = ""
    for e in entries[:15]:
        ts = e.get("timestamp", "")[:16].replace("T", " ")
        src = e.get("source", "?")
        t = e.get("type", "message")
        title = e.get("title", "")
        content = str(e.get("content", ""))[:200]
        feed_html += f"""
        <div class="entry">
          <div class="entry-header">
            {badge(t)}
            <span class="entry-source">{src}</span>
            <span class="entry-title">{title}</span>
            <span class="entry-time">{ts}</span>
          </div>
          <div class="entry-content">{content}</div>
        </div>"""

    success_html = f'<div class="success-msg">✅ {msg}</div>' if msg else ""

    content = f"""
    {success_html}
    <div class="grid">
      <div class="card"><div class="stat">{stats['total']}</div><div class="stat-label">MELDINGER TOTALT</div></div>
      <div class="card"><div class="stat">{stats['tasks']}</div><div class="stat-label">OPPGAVER I KØEN</div></div>
    </div>

    <div class="task-form">
      <h2>Post oppgave til NEXUS</h2>
      <form method="post" action="/task">
        <textarea id="task-input" name="task" placeholder="Eks: Hent 50 nye leads fra Apollo og send kald e-post til alle med score 8+" required></textarea>
        <div class="form-row" style="margin-top:12px;">
          <div></div>
          <select name="agent">
            <option value="nexus">→ NEXUS</option>
            <option value="jordan">→ Jordan</option>
            <option value="all">→ Alle agenter</option>
          </select>
          <button type="submit">SEND OPPGAVE ▶</button>
        </div>
      </form>
      <div class="quick-tasks">
        <button class="quick-btn">Hent 50 leads fra Apollo nå</button>
        <button class="quick-btn">Send kald e-post til alle score 7+</button>
        <button class="quick-btn">Generer daglig rapport</button>
        <button class="quick-btn">Sjekk Instantly-kampanje status</button>
        <button class="quick-btn">Skriv LinkedIn-post om AI for SMB</button>
        <button class="quick-btn">Ring de 10 beste leadsene</button>
      </div>
    </div>

    <div class="actions-bar">
      <form method="post" action="/run/research"><button type="submit" class="secondary">🔍 Kjør Research</button></form>
      <form method="post" action="/run/sales"><button type="submit" class="secondary">📧 Kjør Sales</button></form>
      <form method="post" action="/run/report"><button type="submit" class="secondary">📊 Generer Rapport</button></form>
      <form method="post" action="/run/mcp"><button type="submit" class="secondary">📬 Sjekk MCP-board</button></form>
    </div>

    <div class="feed">
      <h2>Live Agent Feed</h2>
      {feed_html or '<div style="color:#444;padding:20px 0;">Ingen meldinger ennå.</div>'}
    </div>
    """

    html = HTML_BASE.format(time=datetime.now().strftime("%d.%m.%Y %H:%M"), content=content)
    return HTMLResponse(html)


@app.post("/task")
async def post_task(
    request: Request,
    task: str = Form(...),
    agent: str = Form("nexus"),
    user: str = Depends(verify),
):
    from tools.mcp_board import board
    target = f"[{agent.upper()}]" if agent != "all" else "[ALL AGENTS]"
    board.post(
        type="task",
        title=f"{target} {task[:80]}",
        content=task,
        metadata={"target_agent": agent, "posted_by": "nicholas_dashboard"},
    )
    return RedirectResponse(f"/?msg=Oppgave+sendt+til+{agent}", status_code=303)


@app.post("/run/{task_type}")
async def trigger_run(task_type: str, user: str = Depends(verify)):
    import asyncio
    task_map = {
        "research": "Hent leads",
        "sales": "Send e-poster",
        "report": "Generer rapport",
        "mcp": "Sjekk MCP-board",
    }
    label = task_map.get(task_type, task_type)

    def _run():
        import sys
        sys.path.insert(0, "/opt/nexus")
        from main import run
        run(task=label, task_type=task_type)

    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run)
    return RedirectResponse(f"/?msg={label}+startet", status_code=303)


@app.get("/api/feed")
async def api_feed(user: str = Depends(verify)):
    """JSON-API for live feed — kan brukes av Discord-bot."""
    from tools.mcp_board import board
    return JSONResponse(board.read(limit=10))


@app.get("/health")
async def health():
    return {"status": "ok", "service": "NEXUS Dashboard"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
