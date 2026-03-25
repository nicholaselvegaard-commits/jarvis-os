"""
NEXUS Platform v5 — The Office Edition
Port: 8091
"""

import os, sqlite3, secrets, hashlib, json, asyncio, random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Request, Form, Response, Cookie, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from dotenv import load_dotenv

load_dotenv()

BASE_DIR      = Path(__file__).parent
PLATFORM_DB   = str(BASE_DIR / "memory" / "platform.db")
PARENT_DIR    = BASE_DIR.parent

# Cross-system paths (configurable via .env for server)
NEXUS_DB      = Path(os.getenv("NEXUS_DB_PATH",    str(PARENT_DIR/"MAESTRO AGENT"/"nexus"/"nexus.db")))
JORDAN_MEM    = Path(os.getenv("JORDAN_MEM_PATH",  str(PARENT_DIR/"NicholasAI"/"memory")))
NEXUS_MAIN_PY = Path(os.getenv("NEXUS_MAIN_PATH",  str(PARENT_DIR/"MAESTRO AGENT"/"nexus"/"main.py")))

OWNER         = os.getenv("DASHBOARD_USER",         "nicholas")
OWNER_PASS    = os.getenv("DASHBOARD_PASSWORD",      "nexus2026")
TG_TOKEN      = os.getenv("TELEGRAM_TOKEN",          "")
TG_CHAT       = os.getenv("TELEGRAM_OWNER_CHAT_ID", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY",       "")

# ── Agent roster: The Office characters ────────────────────────────
# Layout: Michael's office (back-left), Conference (back-center),
#         Bullpen (center), Annex (right), Reception (front)
AGENTS = {
    # Sales core — Jim & Dwight desks (face each other in bullpen)
    "nexus":    {"name":"NEXUS",      "char":"Jim",     "color":"#4a8ad0","role":"Salg & AI Analyse",
                 "desk_x":-1, "desk_z":1,  "skin":"#c8a870","hair":0x3a2010,"tall":True,
                 "shirt":0x3a6090,"pants":0x1e2030,"voice_pitch":0.95,"voice_rate":1.0,
                 "system":"Du er NEXUS (Jim Halpert), AI-salgssjef hos NEXUS AS. Rolig, analytisk, litt ironisk. Du jobber 24/7 med å finne leads og selge. Svar ALLTID på norsk, maks 2 setninger."},
    "jordan":   {"name":"Jordan",     "char":"Dwight",  "color":"#b0a030","role":"COO & Strategi",
                 "desk_x":-1, "desk_z":-1, "skin":"#c8a070","hair":0x1a0e08,"glasses":True,
                 "shirt":0x7a7020,"pants":0x282820,"voice_pitch":0.8,"voice_rate":0.92,
                 "system":"Du er Jordan (Dwight Schrute), COO hos NEXUS AS. Hyper-effektiv, fakta-orientert. Sier 'Faktum:' foran viktige ting. Svar ALLTID på norsk, maks 2 setninger."},
    # Receptionist — Pam's desk (front center)
    "pam":      {"name":"Pam",        "char":"Pam",     "color":"#c07860","role":"Resepsjonist & Assistent",
                 "desk_x":0,  "desk_z":7,  "skin":"#e0b898","hair":0x7a4018,"female":True,
                 "shirt":0xd09080,"pants":0x606060,"voice_pitch":1.25,"voice_rate":1.05},
    # Sales builders — Jim AI and Dwight AI (opposite row in bullpen)
    "jim_ai":   {"name":"Jim AI",     "char":"Andy",    "color":"#506878","role":"Salg & Prosjekt",
                 "desk_x":3,  "desk_z":1,  "skin":"#c8b080","hair":0x2a1808,
                 "shirt":0x506878,"pants":0x282828,"voice_pitch":1.0,"voice_rate":1.08},
    "dwight_ai":{"name":"Dwight AI",  "char":"Ryan",    "color":"#484820","role":"Bygging & Koding",
                 "desk_x":3,  "desk_z":-1, "skin":"#c8a060","hair":0x0e0808,
                 "shirt":0x484820,"pants":0x181810,"voice_pitch":1.05,"voice_rate":1.1},
    # Annex — HR, Finance
    "angela":   {"name":"Angela HR",  "char":"Angela",  "color":"#a09030","role":"HR & Kvalitetssikring",
                 "desk_x":9,  "desk_z":-2, "skin":"#dcc898","hair":0xd0b028,"female":True,
                 "shirt":0xa09030,"pants":0x484820,"voice_pitch":1.15,"voice_rate":0.9},
    "oscar":    {"name":"Oscar",      "char":"Oscar",   "color":"#483880","role":"Finans & API Credits",
                 "desk_x":11, "desk_z":0,  "skin":"#c09878","hair":0x080818,"glasses":True,
                 "shirt":0x483880,"pants":0x202040,"voice_pitch":0.9,"voice_rate":1.0},
    # Engineering genius team (left bullpen / engineering corner)
    "leonardo": {"name":"Leonardo",   "char":"Toby",    "color":"#2a4060","role":"Ingeniør & Arkitekt",
                 "desk_x":-7, "desk_z":1,  "skin":"#c8b080","hair":0x503010,"tall":True,
                 "shirt":0x2a4060,"pants":0x283040,"voice_pitch":0.85,"voice_rate":0.95},
    "albert":   {"name":"Albert",     "char":"Stanley", "color":"#503838","role":"Algoritme & Matte",
                 "desk_x":-7, "desk_z":-1, "skin":"#b08068","hair":0xe8e8e0,
                 "shirt":0x503838,"pants":0x302020,"voice_pitch":0.75,"voice_rate":0.88},
    "ada":      {"name":"Ada",        "char":"Phyllis", "color":"#385038","role":"Kode & System Design",
                 "desk_x":-9, "desk_z":1,  "skin":"#c8a870","hair":0x1a1020,"female":True,
                 "shirt":0x385038,"pants":0x303828,"voice_pitch":1.1,"voice_rate":1.0},
    "nikola":   {"name":"Nikola",     "char":"Kevin",   "color":"#383058","role":"Innovation & Systems",
                 "desk_x":-9, "desk_z":-1, "skin":"#c0a068","hair":0x281810,
                 "shirt":0x383058,"pants":0x282838,"voice_pitch":0.85,"voice_rate":0.95},
    # Research/Data
    "meredith": {"name":"Meredith",   "char":"Meredith","color":"#603040","role":"Research & Data",
                 "desk_x":6,  "desk_z":1,  "skin":"#d0a880","hair":0x4a1818,"female":True,
                 "shirt":0x603040,"pants":0x402030,"voice_pitch":1.05,"voice_rate":1.1},
}

# Conference room seats (around long table at x=-3, z=-8)
CONF_SEATS = [
    {"x":-5.5,"z":-7},{"x":-3.5,"z":-7},{"x":-1.5,"z":-7},{"x":0.5,"z":-7},
    {"x":-5.5,"z":-9},{"x":-3.5,"z":-9},{"x":-1.5,"z":-9},{"x":0.5,"z":-9},
    {"x":-6.5,"z":-8},{"x":1.5,"z":-8},
]

# ── Integration Bridge — reads NEXUS brain + Jordan memory ────────
def bridge_nexus_stats() -> Dict[str, Any]:
    """Read real KPIs from NEXUS's SQLite database"""
    out = {"leads_total":0,"emails_sent":0,"replies":0,"revenue_est":0,"active":False}
    try:
        if NEXUS_DB.exists():
            out["active"] = True
            db2 = sqlite3.connect(str(NEXUS_DB)); db2.row_factory = sqlite3.Row
            tables = {r[0] for r in db2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "leads" in tables:
                r = db2.execute("SELECT COUNT(*) t, SUM(CASE WHEN emailed_at IS NOT NULL THEN 1 ELSE 0 END) e, SUM(CASE WHEN replied=1 THEN 1 ELSE 0 END) re FROM leads").fetchone()
                if r: out.update({"leads_total":r["t"] or 0,"emails_sent":r["e"] or 0,"replies":r["re"] or 0})
                out["revenue_est"] = int(out["replies"] * 0.12 * 15000)
            if "daily_stats" in tables:
                last = db2.execute("SELECT revenue FROM daily_stats ORDER BY date DESC LIMIT 1").fetchone()
                if last and last["revenue"]: out["revenue_est"] = last["revenue"]
            db2.close()
    except Exception as e: print(f"[Bridge NEXUS] {e}")
    return out

def bridge_jordan_status() -> Dict[str, Any]:
    """Read Jordan's current status from NicholasAI memory"""
    out = {"current_task":"Analyserer markedet...","recent":[]}
    try:
        lt = JORDAN_MEM / "long_term.json"
        if lt.exists():
            d = json.loads(lt.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("current_task"):
                out["current_task"] = str(d["current_task"])[:120]
        cd = JORDAN_MEM / "conversations"
        if cd.exists():
            files = sorted(cd.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:1]
            for f in files:
                msgs = json.loads(f.read_text(encoding="utf-8"))
                out["recent"] = [str(m.get("content",""))[:80] for m in (msgs[-3:] if isinstance(msgs,list) else []) if isinstance(m, dict)]
    except Exception as e: print(f"[Bridge Jordan] {e}")
    return out

async def trigger_nexus_run(task_type: str = "research") -> bool:
    """Try to trigger a real NEXUS run via subprocess"""
    if NEXUS_MAIN_PY.exists():
        try:
            venv_py = NEXUS_MAIN_PY.parent / "venv" / "bin" / "python"
            py = str(venv_py) if venv_py.exists() else "python3"
            proc = await asyncio.create_subprocess_exec(
                py, str(NEXUS_MAIN_PY), "--task", task_type,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                cwd=str(NEXUS_MAIN_PY.parent))
            asyncio.create_task(proc.wait())
            return True
        except Exception as e: print(f"[NEXUS trigger] {e}")
    return False

async def post_to_jordan(message: str):
    """Write a task to Jordan's incoming queue + Telegram"""
    try:
        queue = JORDAN_MEM / "platform_tasks.json"
        tasks = json.loads(queue.read_text(encoding="utf-8")) if queue.exists() else []
        tasks.append({"message":message,"from":"nexus_platform","created_at":datetime.utcnow().isoformat(),"status":"pending"})
        queue.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
    except Exception as e: print(f"[Jordan queue] {e}")
    await send_telegram(f"📋 *Oppgave til Jordan:*\n{message}")

# ── Background Autonomous Worker ──────────────────────────────────
_worker_task = None
async def autonomous_worker():
    """Every 18 min: agents autonomously work, generate ideas, sync KPIs"""
    await asyncio.sleep(60)  # Wait 1 min after startup
    while True:
        try:
            if not ANTHROPIC_KEY:
                await asyncio.sleep(18*60); continue
            import anthropic as ac
            client = ac.Anthropic(api_key=ANTHROPIC_KEY)

            # Read real data from NEXUS brain
            nstats = bridge_nexus_stats()
            jstatus = bridge_jordan_status()

            # NEXUS reports live status
            nexus_sys = AGENTS["nexus"].get("system","Du er NEXUS. Svar på norsk.")
            ctx = f"Leads funnet: {nstats['leads_total']}, Epost sendt: {nstats['emails_sent']}, Svar mottatt: {nstats['replies']}, Estimert inntekt: {nstats['revenue_est']} NOK."
            nexus_txt = await asyncio.to_thread(lambda: client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=120,
                system=nexus_sys,
                messages=[{"role":"user","content":f"Gi en kort statusoppdatering. {ctx}"}]
            ).content[0].text)
            await broadcast({"type":"agent_chat","agent":"nexus","text":nexus_txt[:130]})
            db2 = get_db()
            db2.execute("INSERT INTO agent_activity(agent,activity,position) VALUES(?,?,?)",("nexus",nexus_txt[:250],"desk"))
            today = datetime.utcnow().strftime("%Y-%m-%d")
            db2.execute("""INSERT INTO kpi_daily(date,leads_found,emails_sent,revenue,tasks_done,replies)
                VALUES(?,?,?,?,0,?) ON CONFLICT(date) DO UPDATE SET
                leads_found=excluded.leads_found, emails_sent=excluded.emails_sent,
                revenue=excluded.revenue, replies=excluded.replies""",
                (today,nstats["leads_total"],nstats["emails_sent"],nstats["revenue_est"],nstats["replies"]))
            db2.commit(); db2.close()
            await broadcast({"type":"kpi","data":{"emails_sent":nstats["emails_sent"],"leads_found":nstats["leads_total"],"revenue":nstats["revenue_est"],"tasks_done":0}})
            await asyncio.sleep(8)

            # Jordan checks in
            await broadcast({"type":"agent_chat","agent":"jordan","text":"📊 "+jstatus["current_task"][:90]})
            await asyncio.sleep(6)

            # Random agent generates a revenue idea
            thinker = random.choice(list(AGENTS.keys()))
            ag_sys = AGENTS[thinker].get("system","Svar på norsk.")
            idea_txt = await asyncio.to_thread(lambda: client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=90,
                system=ag_sys,
                messages=[{"role":"user","content":"Gi én konkret idé for å øke inntektene til NEXUS AS denne uken."}]
            ).content[0].text)
            await broadcast({"type":"agent_chat","agent":thinker,"text":"💡 "+idea_txt[:110]})
            db2 = get_db()
            db2.execute("INSERT INTO agent_ideas(agent,idea,category) VALUES(?,?,?)",(thinker,idea_txt[:500],"revenue"))
            db2.commit(); db2.close()
            await broadcast({"type":"new_idea","idea":{"agent":thinker,"idea":idea_txt[:500],"category":"revenue","created_at":datetime.utcnow().isoformat()}})

        except Exception as e:
            print(f"[Worker] {e}")
        await asyncio.sleep(18*60)

# ── DB ──────────────────────────────────────────────────────────────
def get_db():
    c = sqlite3.connect(PLATFORM_DB, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c

def init_db():
    os.makedirs(os.path.dirname(PLATFORM_DB), exist_ok=True)
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, display_name TEXT,
            password_hash TEXT NOT NULL, role TEXT DEFAULT 'user',
            avatar_color TEXT DEFAULT '#7c3aed',
            created_at TEXT DEFAULT (datetime('now')), last_seen TEXT
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL, activity TEXT NOT NULL,
            position TEXT DEFAULT 'desk', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, description TEXT,
            assigned_to TEXT DEFAULT 'all', posted_by TEXT NOT NULL,
            status TEXT DEFAULT 'pending', priority INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS agent_ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT NOT NULL, idea TEXT NOT NULL,
            category TEXT DEFAULT 'general', created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS kpi_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            emails_sent INTEGER DEFAULT 0, leads_found INTEGER DEFAULT 0,
            revenue INTEGER DEFAULT 0, tasks_done INTEGER DEFAULT 0
        );
    """)
    pw = hashlib.sha256(OWNER_PASS.encode()).hexdigest()
    db.execute("INSERT OR IGNORE INTO users (username,display_name,password_hash,role,avatar_color) VALUES(?,?,?,'admin','#e8632a')",
               (OWNER, "Nicholas", pw))
    db.commit(); db.close()

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def create_session(uid):
    t = secrets.token_urlsafe(32)
    exp = (datetime.utcnow()+timedelta(days=30)).isoformat()
    db = get_db(); db.execute("INSERT INTO sessions VALUES(?,?,?)",(t,uid,exp)); db.commit(); db.close()
    return t
def get_user(session: Optional[str] = Cookie(default=None)):
    if not session: return None
    db = None
    try:
        db = get_db()
        r = db.execute("""SELECT u.id,u.username,u.display_name,u.role,u.avatar_color
            FROM sessions s JOIN users u ON s.user_id=u.id
            WHERE s.token=? AND s.expires_at>datetime('now')""",(session,)).fetchone()
        if r:
            try:
                db.execute("UPDATE users SET last_seen=datetime('now') WHERE id=?",(r["id"],))
                db.commit()
            except Exception:
                pass
        return dict(r) if r else None
    except Exception:
        return None
    finally:
        if db:
            try: db.close()
            except: pass
def req_login(u=Depends(get_user)):
    if not u: raise HTTPException(302, headers={"Location":"/login"}); return u
def req_admin(u=Depends(get_user)):
    if not u or u["role"]!="admin": raise HTTPException(403); return u

# ── SSE ─────────────────────────────────────────────────────────────
_subs: List[asyncio.Queue] = []
async def broadcast(d):
    m = json.dumps(d)
    for q in list(_subs):
        try: q.put_nowait(m)
        except: pass
async def sse_gen(req: Request):
    q = asyncio.Queue(); _subs.append(q)
    try:
        while True:
            if await req.is_disconnected(): break
            try:
                d = await asyncio.wait_for(q.get(), timeout=25)
                yield f"data: {d}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type':'ping'})}\n\n"
    finally:
        if q in _subs: _subs.remove(q)

# ── Telegram ────────────────────────────────────────────────────────
async def send_telegram(msg: str):
    if not TG_TOKEN or not TG_CHAT: return
    try:
        import urllib.request
        data = json.dumps({"chat_id":TG_CHAT,"text":msg,"parse_mode":"Markdown"}).encode()
        req2 = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=data, headers={"Content-Type":"application/json"})
        await asyncio.to_thread(urllib.request.urlopen, req2)
    except Exception as e:
        print(f"Telegram error: {e}")

# ── Claude AI task processing ────────────────────────────────────────
async def process_task_with_ai(task_id: int, title: str, assigned_to: str):
    if not ANTHROPIC_KEY: return
    try:
        import anthropic as ac
        client = ac.Anthropic(api_key=ANTHROPIC_KEY)

        # All agents walk to conference room
        for i, ak in enumerate(list(AGENTS.keys())):
            seat = CONF_SEATS[i % len(CONF_SEATS)]
            await broadcast({"type":"agent_move","agent":ak,"x":seat["x"],"z":seat["z"],"text":"Går til møte..."})
            await asyncio.sleep(0.1)
        await asyncio.sleep(2.5)

        # NEXUS analyzes
        await broadcast({"type":"agent_chat","agent":"nexus","text":"🤔 Analyserer oppgaven..."})
        nexus_txt = await asyncio.to_thread(lambda: client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=180,
            system="Du er NEXUS (Jim Halpert). AI-salgsagent på NEXUS kontor. Svar på norsk, 2 setninger, direkte og konkret.",
            messages=[{"role":"user","content":f"Ny oppgave: {title}"}]
        ).content[0].text)
        await broadcast({"type":"agent_chat","agent":"nexus","text":nexus_txt[:120]})
        db = get_db()
        db.execute("INSERT INTO agent_activity(agent,activity,position) VALUES(?,?,?)",("nexus",nexus_txt[:250],"conference"))
        db.commit(); db.close()
        await send_telegram(f"🤖 *NEXUS* — Ny oppgave:\n_{title}_\n\n{nexus_txt}")
        await asyncio.sleep(2.5)

        # Jordan plans
        await broadcast({"type":"agent_chat","agent":"jordan","text":"📋 Lager handlingsplan..."})
        jordan_txt = await asyncio.to_thread(lambda: client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=180,
            system="Du er Jordan (Dwight Schrute). AI-COO på NEXUS kontor. Svar på norsk, lag 2-3 konkrete steg.",
            messages=[{"role":"user","content":f"Planlegg: {title}\nNEXUS: {nexus_txt}"}]
        ).content[0].text)
        await broadcast({"type":"agent_chat","agent":"jordan","text":jordan_txt[:120]})
        db = get_db()
        db.execute("INSERT INTO agent_activity(agent,activity,position) VALUES(?,?,?)",("jordan",jordan_txt[:250],"conference"))
        db.commit(); db.close()
        await send_telegram(f"🧠 *Jordan* — Plan:\n_{title}_\n\n{jordan_txt}")
        await asyncio.sleep(2.5)

        # Pam confirms
        await broadcast({"type":"agent_chat","agent":"pam","text":"Notert! Jeg følger opp."})
        await asyncio.sleep(1.5)

        # Mark in_progress
        db = get_db()
        db.execute("UPDATE tasks SET status='in_progress',updated_at=datetime('now') WHERE id=?",(task_id,))
        db.commit(); db.close()
        await broadcast({"type":"task_update","id":task_id,"status":"in_progress"})
        await asyncio.sleep(4)

        # Everyone back to desks
        for ak, ad in AGENTS.items():
            await broadcast({"type":"agent_move","agent":ak,"x":ad["desk_x"],"z":ad["desk_z"],"text":"Tilbake til arbeid"})
            await asyncio.sleep(0.08)
    except Exception as e:
        print(f"AI task error: {e}")

# ── Voice chat handler ───────────────────────────────────────────────
async def handle_voice(message: str, nearby_agents: list):
    if not ANTHROPIC_KEY: return []
    try:
        import anthropic as ac
        client = ac.Anthropic(api_key=ANTHROPIC_KEY)
        async def get_resp(ak):
            ag = AGENTS.get(ak)
            if not ag: return None
            system = (f"Du er {ag['name']} ({ag['char']}), {ag['role']} hos NEXUS AS. "
                     f"Nicholas (direktøren/Michael Scott) snakker til kontoret. "
                     f"Svar ALLTID på norsk. Maks 1-2 setninger. Vær i karakter.")
            txt = await asyncio.to_thread(lambda: client.messages.create(
                model="claude-haiku-4-5-20251001", max_tokens=80,
                system=system,
                messages=[{"role":"user","content":f"Nicholas sier: {message}"}]
            ).content[0].text)
            return {"agent":ak,"text":txt,"name":ag["name"],"color":ag["color"],
                    "pitch":ag.get("voice_pitch",1.0),"rate":ag.get("voice_rate",1.0)}
        tasks2 = [get_resp(ak) for ak in nearby_agents[:4]]
        results = await asyncio.gather(*tasks2, return_exceptions=True)
        return [r for r in results if r and not isinstance(r, Exception)]
    except Exception as e:
        print(f"Voice error: {e}"); return []

# ── FastAPI ──────────────────────────────────────────────────────────
app = FastAPI(title="NEXUS Platform", docs_url=None, redoc_url=None)

@app.on_event("startup")
async def startup():
    init_db()
    asyncio.create_task(autonomous_worker())

LOGIN_HTML = """<!DOCTYPE html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>NEXUS Login</title><style>*{margin:0;box-sizing:border-box}body{background:#2a2420;font-family:'Courier New',monospace;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#1e1a16;border:1px solid #3a2a1a;padding:40px;border-radius:6px;width:340px;text-align:center}
h1{color:#e8632a;font-size:22px;margin-bottom:4px;letter-spacing:2px}p{color:#4a3020;font-size:10px;margin-bottom:28px}
input{width:100%;padding:10px 14px;background:#161210;border:1px solid #3a2010;color:#d0b890;border-radius:4px;font-family:'Courier New',monospace;font-size:13px;margin-bottom:12px}
button{width:100%;padding:11px;background:#7c3aed;color:#fff;border:none;border-radius:4px;cursor:pointer;font-family:'Courier New',monospace;font-size:13px}
button:hover{background:#6d28d9}.err{color:#ef4444;font-size:11px;margin-top:8px}
.inv{margin-top:20px;font-size:9px;color:#2a1808}a{color:#6a4028;font-size:9px}</style></head>
<body><div class=box><h1>⬡ NEXUS</h1><p>AI COMMAND CENTER · {DEV}</p><!--E-->
<form method=post><input name=username placeholder=brukernavn autocomplete=username>
<input name=password type=password placeholder=passord autocomplete=current-password>
<button>LOGG INN →</button></form>
<div class=inv>Invitert? <a href=/register/nexus-invite-2026>Registrer her</a></div></div></body></html>"""

REG_HTML = """<!DOCTYPE html><html><head><meta charset=utf-8><title>Registrer</title>
<style>*{margin:0;box-sizing:border-box}body{background:#2a2420;font-family:'Courier New',monospace;display:flex;align-items:center;justify-content:center;min-height:100vh}
.box{background:#1e1a16;border:1px solid #3a2a1a;padding:40px;border-radius:6px;width:340px;text-align:center}
h1{color:#e8632a;font-size:18px;margin-bottom:20px}input{width:100%;padding:10px 14px;background:#161210;border:1px solid #3a2010;color:#d0b890;border-radius:4px;font-family:'Courier New',monospace;font-size:13px;margin-bottom:12px}
button{width:100%;padding:11px;background:#16a34a;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:13px}.err{color:#ef4444;font-size:11px;margin-top:8px}</style></head>
<body><div class=box><h1>⬡ NEXUS — Registrer</h1><!--E-->
<form method=post><input name=username placeholder=brukernavn><input name=display_name placeholder="ditt navn">
<input name=password type=password placeholder=passord><button>REGISTRER →</button></form></div></body></html>"""

@app.get("/login",response_class=HTMLResponse)
async def login_page(request:Request):
    ua=request.headers.get("user-agent","").lower()
    mob=any(x in ua for x in ["mobile","android","iphone","ipad"])
    return HTMLResponse(LOGIN_HTML.replace("{DEV}","MOBIL" if mob else "PC"))
@app.post("/login")
async def do_login(response:Response,username:str=Form(...),password:str=Form(...)):
    db=get_db()
    u=db.execute("SELECT * FROM users WHERE username=? AND password_hash=?",(username.lower(),hash_pw(password))).fetchone()
    db.close()
    if not u: return HTMLResponse(LOGIN_HTML.replace("{DEV}","PC").replace("<!--E-->","<div class=err>Feil brukernavn eller passord</div>"))
    t=create_session(u["id"]); r=RedirectResponse("/",status_code=303)
    r.set_cookie("session",t,httponly=True,max_age=60*60*24*30); return r
@app.post("/logout")
async def logout():
    r=RedirectResponse("/login",status_code=303); r.delete_cookie("session"); return r
@app.get("/register/{code}",response_class=HTMLResponse)
async def reg_page(code:str):
    if code!="nexus-invite-2026": return HTMLResponse("<h1>Ugyldig</h1>",status_code=403)
    return HTMLResponse(REG_HTML)
@app.post("/register/{code}")
async def do_reg(code:str,username:str=Form(...),display_name:str=Form(...),password:str=Form(...)):
    if code!="nexus-invite-2026": raise HTTPException(403)
    db=get_db()
    try: db.execute("INSERT INTO users(username,display_name,password_hash) VALUES(?,?,?)",(username.lower(),display_name,hash_pw(password))); db.commit()
    except sqlite3.IntegrityError: db.close(); return HTMLResponse(REG_HTML.replace("<!--E-->","<div class=err>Brukernavn tatt</div>"))
    u=db.execute("SELECT id FROM users WHERE username=?",(username.lower(),)).fetchone(); db.close()
    t=create_session(u["id"]); r=RedirectResponse("/",status_code=303)
    r.set_cookie("session",t,httponly=True,max_age=60*60*24*30); return r

@app.get("/",response_class=HTMLResponse)
async def office(request:Request,user=Depends(get_user)):
    if not user:
        return RedirectResponse("/login",status_code=302)
    db=get_db()
    tasks_data=[dict(t) for t in db.execute("SELECT * FROM tasks ORDER BY priority DESC,created_at DESC LIMIT 30").fetchall()]
    ideas_data=[dict(i) for i in db.execute("SELECT * FROM agent_ideas ORDER BY created_at DESC LIMIT 20").fetchall()]
    feed_data =[dict(a) for a in db.execute("SELECT * FROM agent_activity ORDER BY created_at DESC LIMIT 50").fetchall()]
    users_data=[dict(u) for u in db.execute("SELECT username,display_name,role,last_seen FROM users ORDER BY role DESC").fetchall()]
    krow=db.execute("SELECT * FROM kpi_daily ORDER BY date DESC LIMIT 1").fetchone()
    kpi=dict(krow) if krow else {}; db.close()
    ag_js={k:{"name":v["name"],"char":v["char"],"color":v["color"],"role":v["role"],
               "pitch":v.get("voice_pitch",1.0),"rate":v.get("voice_rate",1.0)} for k,v in AGENTS.items()}
    ag_pos={k:{"x":v["desk_x"],"z":v["desk_z"]} for k,v in AGENTS.items()}
    h=OFFICE_HTML\
        .replace("{UNAME}",  user.get("display_name") or user["username"])\
        .replace("{UROLE}",  user["role"])\
        .replace("{UCOLOR}", user.get("avatar_color","#e8632a"))\
        .replace("{TASKS}",  json.dumps(tasks_data))\
        .replace("{IDEAS}",  json.dumps(ideas_data))\
        .replace("{FEED}",   json.dumps(feed_data))\
        .replace("{USERS}",  json.dumps(users_data))\
        .replace("{AGENTS}", json.dumps(ag_js))\
        .replace("{AGPOS}",  json.dumps(ag_pos))\
        .replace("{CONF}",   json.dumps(CONF_SEATS))\
        .replace("{KPI}",    json.dumps(kpi))\
        .replace("{ADMIN}",  "true" if user["role"]=="admin" else "false")
    return HTMLResponse(h)

@app.get("/api/stream")
async def stream(request:Request,user=Depends(get_user)):
    if not user: raise HTTPException(401)
    return StreamingResponse(sse_gen(request),media_type="text/event-stream",
                             headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.post("/api/tasks")
async def api_task(request:Request,user=Depends(get_user)):
    if not user: raise HTTPException(401)
    body=await request.json()
    title=body.get("title","").strip()
    if not title: return JSONResponse({"ok":False},status_code=400)
    ag=body.get("assigned_to","all")
    db=get_db()
    db.execute("INSERT INTO tasks(title,description,assigned_to,posted_by,priority) VALUES(?,?,?,?,?)",
               (title,body.get("description",""),ag,user["username"],body.get("priority",1)))
    db.commit()
    task=dict(db.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 1").fetchone()); db.close()
    await broadcast({"type":"new_task","task":task})
    asyncio.create_task(process_task_with_ai(task["id"],title,ag))
    return JSONResponse({"ok":True,"task":task})

@app.post("/api/tasks/{tid}/status")
async def task_status(tid:int,request:Request,user=Depends(get_user)):
    body=await request.json(); db=get_db()
    db.execute("UPDATE tasks SET status=?,updated_at=datetime('now') WHERE id=?",(body["status"],tid))
    db.commit(); db.close()
    await broadcast({"type":"task_update","id":tid,"status":body["status"]})
    return JSONResponse({"ok":True})

@app.post("/api/voice")
async def api_voice(request:Request,user=Depends(get_user)):
    if not user: raise HTTPException(401)
    body=await request.json()
    message=body.get("message","").strip()
    nearby=body.get("agents",["nexus","jordan","pam"])
    if not message: return JSONResponse({"responses":[]})
    db=get_db()
    db.execute("INSERT INTO agent_activity(agent,activity,position) VALUES(?,?,?)",
               ("nicholas",f"Sa: {message[:100]}","bullpen"))
    db.commit(); db.close()
    responses=await handle_voice(message,nearby)
    for r in responses:
        await broadcast({"type":"agent_chat","agent":r["agent"],"text":r["text"]})
        db=get_db()
        db.execute("INSERT INTO agent_activity(agent,activity,position) VALUES(?,?,?)",
                   (r["agent"],r["text"][:200],"desk"))
        db.commit(); db.close()
    return JSONResponse({"responses":responses})

@app.post("/api/activity")
async def api_activity(request:Request):
    body=await request.json(); db=get_db()
    db.execute("INSERT INTO agent_activity(agent,activity,position) VALUES(?,?,?)",
               (body["agent"],body["activity"],body.get("position","desk")))
    db.commit(); db.close()
    await broadcast({"type":"activity","agent":body["agent"],"activity":body["activity"],
                     "position":body.get("position","desk")})
    return JSONResponse({"ok":True})

@app.post("/api/ideas")
async def api_idea(request:Request):
    body=await request.json(); db=get_db()
    db.execute("INSERT INTO agent_ideas(agent,idea,category) VALUES(?,?,?)",
               (body["agent"],body["idea"],body.get("category","general")))
    db.commit()
    idea=dict(db.execute("SELECT * FROM agent_ideas ORDER BY id DESC LIMIT 1").fetchone()); db.close()
    await broadcast({"type":"new_idea","idea":idea})
    return JSONResponse({"ok":True})

@app.post("/api/kpi")
async def api_kpi(request:Request):
    body=await request.json(); today=datetime.utcnow().strftime("%Y-%m-%d"); db=get_db()
    db.execute("""INSERT INTO kpi_daily(date,emails_sent,leads_found,revenue,tasks_done) VALUES(?,?,?,?,?)
                  ON CONFLICT(date) DO UPDATE SET emails_sent=excluded.emails_sent,
                  leads_found=excluded.leads_found,revenue=excluded.revenue,tasks_done=excluded.tasks_done""",
               (today,body.get("emails_sent",0),body.get("leads_found",0),body.get("revenue",0),body.get("tasks_done",0)))
    db.commit(); db.close()
    await broadcast({"type":"kpi","data":body})
    return JSONResponse({"ok":True})

@app.get("/health")
async def health(): return {"ok":True,"v":"6.0"}

@app.get("/api/system/status")
async def sys_status(user=Depends(get_user)):
    if not user: raise HTTPException(401)
    nstats = bridge_nexus_stats()
    jstatus = bridge_jordan_status()
    db2 = get_db()
    task_count = db2.execute("SELECT COUNT(*) n FROM tasks").fetchone()["n"]
    idea_count  = db2.execute("SELECT COUNT(*) n FROM agent_ideas").fetchone()["n"]
    act_count   = db2.execute("SELECT COUNT(*) n FROM agent_activity WHERE created_at > datetime('now','-1 hour')").fetchone()["n"]
    db2.close()
    return JSONResponse({"nexus":nstats,"jordan":jstatus,"platform":{"tasks":task_count,"ideas":idea_count,"activity_1h":act_count},"timestamp":datetime.utcnow().isoformat()})

@app.get("/api/nexus/stats")
async def nexus_stats(user=Depends(get_user)):
    if not user: raise HTTPException(401)
    return JSONResponse(bridge_nexus_stats())

@app.get("/api/jordan/status")
async def jordan_status_route(user=Depends(get_user)):
    if not user: raise HTTPException(401)
    return JSONResponse(bridge_jordan_status())

@app.post("/api/trigger/nexus")
async def trigger_nexus(request:Request, user=Depends(get_user)):
    if not user or user["role"]!="admin": raise HTTPException(403)
    body = await request.json()
    task_type = body.get("task_type","research")
    success = await trigger_nexus_run(task_type)
    await broadcast({"type":"agent_chat","agent":"nexus","text":f"🚀 NEXUS {task_type}-kjøring startet!" if success else "⚠️ NEXUS main.py ikke funnet — kjøres lokalt"})
    return JSONResponse({"ok":True,"triggered":success,"task_type":task_type})

@app.post("/api/trigger/jordan")
async def trigger_jordan(request:Request, user=Depends(get_user)):
    if not user: raise HTTPException(401)
    body = await request.json()
    message = body.get("message","Sjekk status og rapporter til Nicholas")
    await post_to_jordan(message)
    await broadcast({"type":"agent_chat","agent":"jordan","text":f"📩 Mottatt oppgave: {message[:80]}"})
    return JSONResponse({"ok":True})

# ── HTML ─────────────────────────────────────────────────────────────
OFFICE_HTML = """<!DOCTYPE html>
<html><head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>NEXUS — The Office</title>
<link rel="preload" href="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js" as="script">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#1a1410;font-family:'Courier New',monospace;overflow:hidden;height:100vh}

#top{position:fixed;top:0;left:0;right:0;height:44px;background:rgba(16,12,8,.96);
  border-bottom:1px solid #3a2010;display:flex;align-items:center;padding:0 10px;gap:6px;z-index:100}
#logo{color:#e8632a;font-size:12px;font-weight:bold;letter-spacing:2px;margin-right:2px}
#ll{flex:1;color:#3a2010;font-size:9px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:300px}
.tbtn{background:none;border:1px solid #3a2010;color:#5a3820;padding:3px 9px;border-radius:3px;cursor:pointer;
  font-family:'Courier New',monospace;font-size:9px;white-space:nowrap;transition:.15s}
.tbtn:hover{border-color:#e8632a;color:#e8632a}.tbtn.on{border-color:#7c3aed;color:#c084fc}
#mic-btn{background:none;border:1px solid #dc2626;color:#dc2626;padding:3px 9px;border-radius:3px;
  cursor:pointer;font-family:'Courier New',monospace;font-size:9px;display:inline-block}
#mic-btn.listening{background:#dc2626;color:#fff;animation:pulse .8s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.6}}

#c{display:block;position:fixed;top:44px;left:0;right:0;bottom:36px}

.bub{position:fixed;background:rgba(16,10,6,.93);border:1px solid #3a1808;color:#d0b890;
  padding:5px 9px;border-radius:7px 7px 7px 1px;font-size:10px;max-width:200px;
  pointer-events:none;z-index:50;line-height:1.4;display:none;box-shadow:0 2px 8px rgba(0,0,0,.4)}

#bot{position:fixed;bottom:0;left:0;right:0;height:36px;background:rgba(16,12,8,.96);
  border-top:1px solid #3a2010;display:flex;align-items:center;padding:0 10px;gap:8px;z-index:100}
#radio{display:flex;align-items:center;gap:5px;flex:1}
.rsong{color:#3a2010;font-size:9px}.rbtn{background:none;border:1px solid #3a2010;color:#5a3820;
  padding:2px 7px;border-radius:3px;cursor:pointer;font-family:'Courier New',monospace;font-size:9px}
.rbtn:hover{color:#e8632a;border-color:#e8632a}
#wui{display:none;color:#3a2010;font-size:9px;gap:8px;flex:1;align-items:center}

#vtip{position:fixed;bottom:46px;left:50%;transform:translateX(-50%);background:rgba(220,38,38,.9);
  color:#fff;padding:6px 16px;border-radius:4px;font-size:10px;font-family:'Courier New',monospace;
  display:none;pointer-events:none;z-index:200}

#panel{position:fixed;right:-380px;top:44px;bottom:36px;width:360px;
  background:rgba(12,8,5,.97);border-left:1px solid #3a2010;
  transition:right .25s ease;z-index:90;display:flex;flex-direction:column}
#panel.open{right:0}
#ptabs{display:flex;border-bottom:1px solid #3a2010}
.ptab{flex:1;padding:9px 4px;text-align:center;color:#3a2010;font-size:9px;cursor:pointer;letter-spacing:1px;transition:.15s}
.ptab:hover{color:#e8632a}.ptab.on{color:#e8632a;border-bottom:1px solid #e8632a}
#pc{flex:1;overflow-y:auto;padding:8px}
#pc::-webkit-scrollbar{width:3px}#pc::-webkit-scrollbar-thumb{background:#3a2010}
.tc{border:1px solid #1e1008;border-radius:4px;padding:9px;margin-bottom:6px;cursor:pointer;background:#0d0806}
.tc:hover{border-color:#3a2010}.th2{display:flex;gap:5px;margin-bottom:4px;align-items:center}
.tt2{color:#c8a870;font-size:11px;margin-bottom:2px}.tm2{color:#2a1808;font-size:9px}
.bx{font-size:8px;padding:2px 5px;border-radius:2px}
.bp{background:#2a1808;color:#f59e0b}.bi{background:#181020;color:#7c3aed}
.bdone{background:#081408;color:#16a34a}.ball{background:#080a18;color:#0ea5e9}
.ic{border-left:2px solid #7c3aed;padding:7px;margin-bottom:5px;background:#0d0806}
.ia{color:#7c3aed;font-size:9px;margin-bottom:2px}.it{color:#c8a870;font-size:11px}
.fi2{display:flex;gap:7px;align-items:flex-start;padding:5px 0;border-bottom:1px solid #180e08}
.fd2{width:5px;height:5px;border-radius:50%;margin-top:4px;flex-shrink:0}
.ft2{flex:1;color:#8a6840;font-size:10px}.ftm2{color:#2a1808;font-size:9px;margin-top:1px}
.pr2{display:flex;align-items:center;gap:9px;padding:7px 0;border-bottom:1px solid #180e08}
.pav2{width:30px;height:30px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:bold}
.pn2{color:#c8a870;font-size:11px}.prole2{color:#2a1808;font-size:9px}
#tform{padding:9px;border-top:1px solid #1e1008}
#nt{width:100%;background:#0d0806;border:1px solid #2a1808;color:#c8a870;padding:7px;border-radius:3px;
  font-family:'Courier New',monospace;font-size:11px;resize:none;height:56px}
#ta{width:100%;margin:5px 0;background:#0d0806;border:1px solid #2a1808;color:#8a6840;
  padding:5px;border-radius:3px;font-family:'Courier New',monospace;font-size:10px}
#tform button{width:100%;padding:7px;background:#7c3aed;color:#fff;border:none;border-radius:3px;
  cursor:pointer;font-family:'Courier New',monospace;font-size:10px}
#tform button:hover{background:#6d28d9}
#toast{position:fixed;bottom:46px;left:50%;transform:translateX(-50%) translateY(0);
  background:rgba(16,8,4,.97);border:1px solid #e8632a;color:#e8632a;padding:8px 18px;
  border-radius:5px;font-size:10px;opacity:0;transition:opacity .3s,transform .3s;
  z-index:200;pointer-events:none;white-space:nowrap;letter-spacing:.5px}
#toast.on{opacity:1;transform:translateX(-50%) translateY(-4px)}

/* Glowing agent names */
@keyframes glow{0%,100%{text-shadow:0 0 4px currentColor}50%{text-shadow:0 0 10px currentColor,0 0 20px currentColor}}
.agent-active{animation:glow 2s infinite}

/* Status bar fade */
@keyframes fadeSlide{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.bub{animation:fadeSlide .25s ease}
</style>
</head><body>

<div id=top>
  <div id=logo>⬡ NEXUS</div>
  <div id=ll>Laster kontoret...</div>
  <button class=tbtn id=wb onclick=toggleWalk()>🚶 Gå (F)</button>
  <button id=mic-btn onclick=toggleMic() title="Krever HTTPS eller Firefox. Alternativt: bruk tekstboks i walk-modus">🎤 Snakk</button>
  <button class=tbtn onclick="openP('tasks')">📋 Oppgaver</button>
  <button class=tbtn onclick="openP('feed')">⚡ Feed</button>
  <button class=tbtn onclick="openP('ideas')">💡 Ideer</button>
  <button class=tbtn onclick="openP('people')">👥 Team</button>
  <div id=adm></div>
  <form method=post action=/logout style=margin:0><button class=tbtn>← Ut</button></form>
</div>

<canvas id=c></canvas>

<!-- speech bubbles — one per agent -->
<div class=bub id=b_nexus    style="border-bottom:2px solid #3a6090"></div>
<div class=bub id=b_jordan   style="border-bottom:2px solid #7a7020"></div>
<div class=bub id=b_pam      style="border-bottom:2px solid #c07860"></div>
<div class=bub id=b_jim_ai   style="border-bottom:2px solid #506878"></div>
<div class=bub id=b_dwight_ai style="border-bottom:2px solid #484820"></div>
<div class=bub id=b_angela   style="border-bottom:2px solid #a09030"></div>
<div class=bub id=b_oscar    style="border-bottom:2px solid #483880"></div>
<div class=bub id=b_leonardo style="border-bottom:2px solid #2a4060"></div>
<div class=bub id=b_albert   style="border-bottom:2px solid #503838"></div>
<div class=bub id=b_ada      style="border-bottom:2px solid #385038"></div>
<div class=bub id=b_nikola   style="border-bottom:2px solid #383058"></div>
<div class=bub id=b_meredith style="border-bottom:2px solid #603040"></div>

<div id=vtip>🎤 Lytter...</div>

<!-- Minimap (walk mode only) -->
<canvas id=mm width=120 height=94 style="position:fixed;bottom:46px;right:8px;border-radius:4px;display:none;z-index:60"></canvas>

<!-- Agent popup when nearby -->
<div id=agpop style="position:fixed;bottom:46px;left:8px;background:rgba(10,6,3,.96);border:1px solid #444;border-radius:6px;padding:9px 14px;display:none;z-index:60;pointer-events:none;min-width:160px">
  <div id=agpop-name style="color:#e8c878;font-size:13px;font-weight:bold;letter-spacing:1px"></div>
  <div id=agpop-char style="color:#604020;font-size:9px;margin-top:3px;letter-spacing:.5px"></div>
  <div id=agpop-hint style="color:#3a2010;font-size:8px;margin-top:4px">↩ ENTER eller V for å snakke</div>
</div>

<!-- Live stats bar (walk mode) -->
<div id=statsbar style="position:fixed;top:54px;right:8px;background:rgba(10,6,3,.9);border:1px solid #2a1808;border-radius:4px;padding:5px 10px;display:none;z-index:60;font-size:9px;font-family:'Courier New',monospace;line-height:1.7">
  <div style="color:#4ade80">Leads: <span id=s-leads>-</span></div>
  <div style="color:#60a5fa">Epost: <span id=s-email>-</span></div>
  <div style="color:#fbbf24">Inntekt: <span id=s-rev>-</span> kr</div>
</div>

<!-- Mouse look hint -->
<div id=mlhint style="position:fixed;top:54px;left:50%;transform:translateX(-50%);background:rgba(20,12,6,.92);color:#5a3820;padding:5px 16px;border-radius:4px;font-size:9px;font-family:'Courier New',monospace;display:none;pointer-events:none;z-index:150;letter-spacing:.3px">🖱 Klikk for mus &nbsp;·&nbsp; WASD = gå &nbsp;·&nbsp; SHIFT = løp &nbsp;·&nbsp; E = chat &nbsp;·&nbsp; V = mikrofon &nbsp;·&nbsp; ESC = avslutt</div>

<div id=panel>
  <div id=ptabs>
    <div class="ptab on" id=tab-tasks  onclick="showTab('tasks')">OPPGAVER</div>
    <div class=ptab       id=tab-feed   onclick="showTab('feed')">FEED</div>
    <div class=ptab       id=tab-ideas  onclick="showTab('ideas')">IDEER</div>
    <div class=ptab       id=tab-people onclick="showTab('people')">TEAM</div>
  </div>
  <div id=pc></div>
  <div id=tform>
    <textarea id=nt placeholder="Skriv oppgave til agentene..."></textarea>
    <select id=ta>
      <option value=all>→ Alle agenter</option>
      <option value=nexus>→ NEXUS</option>
      <option value=jordan>→ Jordan</option>
    </select>
    <button onclick=postTask()>SEND OPPGAVE ▶</button>
  </div>
</div>

<div id=bot>
  <div id=radio>
    <span>📻</span><span class=rsong>Lo-Fi — SomaFM</span>
    <button class=rbtn id=rb onclick=toggleRadio()>▶ Radio</button>
  </div>
  <div id=wui>
    <span style="color:#5a3820;font-size:9px">WASD=gå &nbsp;|&nbsp; MUS=se &nbsp;|&nbsp; V=snakk &nbsp;|&nbsp; ESC=avslutt</span>
    <input id=wci placeholder="Skriv til agentene nærme deg..." style="flex:1;background:#0d0806;border:1px solid #3a1808;color:#c8a870;padding:3px 8px;border-radius:3px;font-family:'Courier New',monospace;font-size:10px;outline:none" onkeydown="if(event.key==='Enter')sendChat()">
    <button onclick=sendChat() style="background:none;border:1px solid #3a2010;color:#5a3820;padding:2px 8px;border-radius:3px;cursor:pointer;font-family:'Courier New',monospace;font-size:9px">Send</button>
  </div>
</div>
<audio id=ra src="https://ice1.somafm.com/lofi-128-mp3" preload=none></audio>
<div id=toast></div>

<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script>
window.onerror=function(msg,s,ln){
  var d=document.createElement('div');
  d.style.cssText='position:fixed;top:52px;left:8px;right:8px;background:#600;color:#fff;padding:8px;z-index:9999;font-size:10px;border-radius:4px;font-family:monospace';
  d.textContent='ERR ln'+ln+': '+msg;document.body.appendChild(d);
};

// ── Data ──────────────────────────────────────────────────────────
var TASKS={TASKS}, IDEAS={IDEAS}, FEED={FEED};
var USERS={USERS}, AGENTS={AGENTS}, KPI={KPI};
var AGPOS={AGPOS}, CONF={CONF};
var IS_ADMIN={ADMIN}, U_COLOR="{UCOLOR}", U_NAME="{UNAME}";

if(IS_ADMIN) document.getElementById('adm').innerHTML=
  '<a href=/admin style="color:#e8632a;font-size:9px;border:1px solid #3a1808;padding:2px 7px;border-radius:3px;text-decoration:none">⚙</a>';

// ── Renderer ──────────────────────────────────────────────────────
var renderer=new THREE.WebGLRenderer({canvas:document.getElementById('c'),antialias:true,powerPreference:'high-performance'});
renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));
renderer.setClearColor(0xb8d4e8); // sky blue exterior

var scene=new THREE.Scene();
scene.fog=new THREE.Fog(0xb8d4e8,22,48);

var camera=new THREE.PerspectiveCamera(60,1,.05,60);

function resize(){
  var w=innerWidth,h=innerHeight-80;
  renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();
}
resize();addEventListener('resize',resize);

// ── Lighting ──────────────────────────────────────────────────────
scene.add(new THREE.AmbientLight(0xfff8f0,1.0));
var sun=new THREE.DirectionalLight(0xfff8f0,.5);
sun.position.set(5,10,5);scene.add(sun);
scene.add(new THREE.HemisphereLight(0xfff4e8,0xd0c8bc,.4));

function pl(x,y,z,c,i,r){var l=new THREE.PointLight(c,i,r);l.position.set(x,y,z);scene.add(l);}

// ── Canvas Textures ────────────────────────────────────────────────
function makeCarpetTex(){
  var cv=document.createElement('canvas');cv.width=256;cv.height=256;
  var c=cv.getContext('2d');
  c.fillStyle='#989080';c.fillRect(0,0,256,256);
  // Subtle cross-hatch pattern
  c.strokeStyle='rgba(0,0,0,.07)';c.lineWidth=1;
  for(var i=0;i<256;i+=8){c.beginPath();c.moveTo(i,0);c.lineTo(i,256);c.stroke();}
  for(var j=0;j<256;j+=8){c.beginPath();c.moveTo(0,j);c.lineTo(256,j);c.stroke();}
  c.strokeStyle='rgba(255,255,255,.04)';c.lineWidth=.5;
  for(var k=0;k<256;k+=4){c.beginPath();c.moveTo(k,0);c.lineTo(256,k);c.stroke();}
  var tex=new THREE.CanvasTexture(cv);tex.repeat.set(6,5);tex.wrapS=tex.wrapT=THREE.RepeatWrapping;
  return tex;
}
function makeWBTex(lines){
  var cv=document.createElement('canvas');cv.width=512;cv.height=256;
  var c=cv.getContext('2d');
  c.fillStyle='#f8f8f4';c.fillRect(0,0,512,256);
  c.fillStyle='rgba(200,190,180,.4)';c.fillRect(0,0,512,256);
  c.font='bold 18px Arial';c.fillStyle='#1a3080';c.textAlign='left';
  (lines||['NEXUS Revenue Plan','Q1: 100,000 NOK','Leads → Email → Demo → Close','Daily: Research + Outreach']).forEach(function(l,i){
    c.fillText(l,24,36+i*44);
    c.fillStyle='#3040a0';c.font='16px Arial';
  });
  c.strokeStyle='rgba(40,80,160,.15)';c.lineWidth=1;
  for(var y=40;y<256;y+=44){c.beginPath();c.moveTo(12,y);c.lineTo(500,y);c.stroke();}
  return new THREE.CanvasTexture(cv);
}

// ── Material cache ─────────────────────────────────────────────────
var _mc={};
function m(col){if(!_mc[col])_mc[col]=new THREE.MeshLambertMaterial({color:col});return _mc[col];}
function mt(col,op){return new THREE.MeshLambertMaterial({color:col,transparent:true,opacity:op});}

function B(w,h,d,x,y,z,col){
  var mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),m(col));
  mesh.position.set(x,y,z);scene.add(mesh);return mesh;
}
function Bt(w,h,d,x,y,z,col,op){
  var mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mt(col,op));
  mesh.position.set(x,y,z);scene.add(mesh);return mesh;
}

// ── THE OFFICE LAYOUT ─────────────────────────────────────────────
// Scene: x -14 to 14 (28 wide), z -11 to 11 (22 deep)
// Camera default: isometric top-down from above

// SKY backdrop (visible through windows)
var skyGeo=new THREE.BoxGeometry(60,20,60);
var skyMat=new THREE.MeshBasicMaterial({color:0x88c0e8,side:THREE.BackSide});
scene.add(new THREE.Mesh(skyGeo,skyMat));
// Ground outside
var outFloor=new THREE.Mesh(new THREE.PlaneGeometry(60,60),new THREE.MeshLambertMaterial({color:0x6a8a60}));
outFloor.rotation.x=-Math.PI/2;outFloor.position.y=-.1;scene.add(outFloor);

// FLOOR — carpet texture
var carpetMat=new THREE.MeshLambertMaterial({map:makeCarpetTex()});
var floorMesh=new THREE.Mesh(new THREE.BoxGeometry(28,.15,22),carpetMat);
floorMesh.position.set(0,-.075,0);scene.add(floorMesh);

// CEILING (hidden in overview, shown in walk mode)
var ceilMesh=B(28,.15,22,0,3.575,0,0xe0dcd4);
ceilMesh.visible=false;

// OUTER WALLS (height 3.5)
B(28,3.5,.3,0,1.75,-11,0xdedad0);  // back
B(28,3.5,.3,0,1.75, 11,0xe8e4dc);  // front
B(.3,3.5,22,-14,1.75,0,0xe4e0d8);  // left
B(.3,3.5,22, 14,1.75,0,0xe4e0d8);  // right

// WINDOWS — back wall and side walls
var wm=mt(0x90b8d8,.25);
[-9,-4,1,6].forEach(function(x){
  var gw=new THREE.Mesh(new THREE.BoxGeometry(2,.05,1.5),wm);gw.position.set(x,2.2,-10.85);scene.add(gw);
  B(2.2,.08,.25,x,2.2,-10.88,0xd8d4cc); // window frame
  pl(x,2,-9.5,0xd0e8ff,.15,4);
});
// Side windows (left wall, x=-14)
[-5,3].forEach(function(z){
  var gw2=new THREE.Mesh(new THREE.BoxGeometry(1.5,.05,2),wm);gw2.position.set(-13.87,2.2,z);scene.add(gw2);
  pl(-12.5,2,z,0xd0e8ff,.1,4);
});

// ── MICHAEL'S OFFICE (back-left) ─────────────────────────────────
// Glass walls: right at x=-7.5, front at z=-4.5
// Solid wall at back (z=-11) and left (x=-14) already exist
var gm=mt(0x90b0c8,.2);
// Right glass wall of Michael's office
Bt(.08,3.5,6.5,-7.5,1.75,-7.75,0x90b0c8,.2);
// Front glass wall
Bt(6.5,3.5,.08,-10.75,1.75,-4.5,0x90b0c8,.2);
// Glass frames
B(.08,3.5,.08,-7.5,1.75,-4.5,0xa8a098);B(.08,3.5,.08,-7.5,1.75,-11,0xa8a098);
B(.08,.08,6.5,-7.5,3.5,-7.75,0xa8a098);B(.08,.08,6.5,-7.5,.08,-7.75,0xa8a098);
B(6.5,.08,.08,-10.75,3.5,-4.5,0xa8a098);B(6.5,.08,.08,-10.75,.08,-4.5,0xa8a098);
// Door opening (gap in front glass wall — implied, not physical)

// Michael's office furniture
// His big desk (L-shaped implied)
var md=new THREE.Group();
var mdt=new THREE.Mesh(new THREE.BoxGeometry(2.2,.07,1.1),m(0x9a7850));mdt.position.y=.92;md.add(mdt);
var mdc=new THREE.Mesh(new THREE.BoxGeometry(2.2,.92,.6),m(0x7a6040));mdc.position.set(0,.46,-.25);md.add(mdc);
var mdm=new THREE.Mesh(new THREE.BoxGeometry(.7,.5,.04),m(0x101010));mdm.position.set(0,1.37,-.4);md.add(mdm);
var mdms=new THREE.Mesh(new THREE.BoxGeometry(.62,.44,.02),m(0x0a1828));mdms.material=new THREE.MeshLambertMaterial({color:0x0a1828,emissive:0x0a1828,emissiveIntensity:.5});
mdms.position.set(0,1.37,-.39);md.add(mdms);
md.position.set(-11,-0,-8.5);scene.add(md);
// Couch (grey)
B(2.2,.55,.8,-12,.28,-6,0x909090);B(2.2,.55,.1,-12,.28,-5.65,0x787878);B(2.2,.5,.55,-12.8,.52,-5.88,0x787878); // armrest
// Michael's chair
B(.48,.07,.48,-11,.7,-7.8,0x282828);B(.48,.46,.06,-11,.93,-7.6,0x282828);
// Small table + chairs (visitor)
B(.9,.05,.9,-12.8,.77,-8.3,0x9a7850);
// Bookshelf on back wall
B(1.5,.08,2.5,-13,.5,-9.8,0x8a7048);B(1.5,.08,2.5,-13,1.,-9.8,0x8a7048);B(1.5,.08,2.5,-13,1.5,-9.8,0x8a7048);B(1.5,3,.08,-13,1.5,-10.85,0x7a6038);
// Dundies Award trophies (gold!) on bookshelf
[-.15,0,.15].forEach(function(ox){
  var base=new THREE.Mesh(new THREE.CylinderGeometry(.05,.07,.06,8),new THREE.MeshLambertMaterial({color:0xc8a020}));
  base.position.set(-13+ox,1.61,-9.8);scene.add(base);
  var trophy=new THREE.Mesh(new THREE.CylinderGeometry(.02,.035,.22,8),new THREE.MeshLambertMaterial({color:0xd4a818,emissive:0x402808,emissiveIntensity:.3}));
  trophy.position.set(-13+ox,1.76,-9.8);scene.add(trophy);
  var cup=new THREE.Mesh(new THREE.CylinderGeometry(.055,.02,.1,8),new THREE.MeshLambertMaterial({color:0xd4a818,emissive:0x402808,emissiveIntensity:.3}));
  cup.position.set(-13+ox,1.93,-9.8);scene.add(cup);
});
// "Dundie Award" sign on shelf
(function(){var cv=document.createElement('canvas');cv.width=128;cv.height=32;
var c=cv.getContext('2d');c.fillStyle='rgba(16,10,4,.0)';c.fillRect(0,0,128,32);
c.font='bold 11px Arial';c.fillStyle='#c8a020';c.textAlign='center';c.fillText('🏆 DUNDIE AWARDS',64,22);
var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv),transparent:true}));
sp.scale.set(.9,.22,1);sp.position.set(-13,2.1,-9.8);scene.add(sp);})();
// Framed award on wall
B(.55,.42,.04,-13.8,2.0,-9.0,0xd4c090);B(.45,.32,.04,-13.8,2.0,-8.98,0xfaf8ee);
// Light in Michael's office
pl(-11,2.8,-7.5,0xfff0d0,.5,9);

// ── CONFERENCE ROOM (back-center) ────────────────────────────────
// Bounded: x -7.5 to 2, z -11 to -5
// Glass front wall at z=-5
Bt(9.5,3.5,.08,-2.75,1.75,-5,0x90b0c8,.18);
// Right wall (solid)
B(.08,3.5,6,-2,1.75,-8,0xdedad0);
// Frame
B(9.5,.08,.08,-2.75,3.5,-5,0xa8a098);B(9.5,.08,.08,-2.75,.08,-5,0xa8a098);
// Long conference table
var ct=new THREE.Mesh(new THREE.BoxGeometry(7,.09,2.4),m(0x7a6040));ct.position.set(-5,.91,-8);scene.add(ct);
B(.1,.91,.1,-5,.455,-8,0x5a4030); // center leg
// Conference chairs (10 around table)
[[-.5,-6.8],[-.5,-9.2],[-2,-6.8],[-2,-9.2],[-3.5,-6.8],[-3.5,-9.2],[-5,-6.8],[-5,-9.2],[-8.2,-8],[1.2,-8]].forEach(function(p){
  var cg=new THREE.Group();
  var cs=new THREE.Mesh(new THREE.BoxGeometry(.4,.06,.4),m(0x282828));cs.position.y=.68;cg.add(cs);
  var cb=new THREE.Mesh(new THREE.BoxGeometry(.4,.4,.05),m(0x282828));cb.position.set(0,.89,-.17);cg.add(cb);
  cg.position.set(p[0],0,p[1]);scene.add(cg);
});
// Whiteboard with revenue plan writing
var wbMat=new THREE.MeshLambertMaterial({map:makeWBTex()});
var wbMesh=new THREE.Mesh(new THREE.BoxGeometry(4,.05,1.6),wbMat);
wbMesh.position.set(-5,2.3,-10.84);scene.add(wbMesh);
B(.04,1.7,4.1,-5,2.25,-10.85,0xd0ccc4); // whiteboard frame
// Conference room light
pl(-5,2.8,-8,0xfff8e8,.35,8);
// Label
(function(){var cv=document.createElement('canvas');cv.width=256;cv.height=44;
var c=cv.getContext('2d');c.fillStyle='rgba(240,236,228,.9)';c.fillRect(0,0,256,44);
c.font='bold 18px Arial';c.fillStyle='#2a4060';c.textAlign='center';c.fillText('Conference Room',128,30);
var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv),transparent:true}));
sp.scale.set(2,.35,1);sp.position.set(-4.5,3.3,-5.1);scene.add(sp);})();

// ── BULLPEN ───────────────────────────────────────────────────────
// Main open area: x -13.5 to 6, z -4.5 to 7.5
// Low partition walls (cubicle dividers) between desk clusters
function partition(x,z,w,d,ry){
  var pg=new THREE.Group();
  var pw=new THREE.Mesh(new THREE.BoxGeometry(w,1.3,d),m(0xd0ccb8));
  pw.position.set(0,.65,0);pg.add(pw);
  // Top trim
  var pt=new THREE.Mesh(new THREE.BoxGeometry(w,.06,d),m(0xa09080));
  pt.position.set(0,1.33,0);pg.add(pt);
  pg.position.set(x,0,z);pg.rotation.y=ry||0;scene.add(pg);
}
// Partition rows between desk clusters
partition(-2.5,-1.8,4,.1,0); // between Dwight/Jim rows and annex
partition(5.2, 0, .1,8,0);   // partition before annex

// ── DESK + CHAIR helper ───────────────────────────────────────────
var _scrColors=[0x0a2040,0x0a1a30,0x0a2818,0x1a0a28,0x280a18];var _scrIdx=0;
function mkDesk(x,z,ry){
  var g=new THREE.Group();
  // Desk surface (dark wood)
  var top=new THREE.Mesh(new THREE.BoxGeometry(1.6,.07,.9),new THREE.MeshPhongMaterial({color:0x6a4c28,specular:0x3a2010,shininess:18}));
  top.position.y=.89;g.add(top);
  var cab=new THREE.Mesh(new THREE.BoxGeometry(1.6,.89,.55),m(0x5a3c1e));cab.position.set(0,.445,-.18);g.add(cab);
  // Monitor casing
  var mon=new THREE.Mesh(new THREE.BoxGeometry(.64,.48,.045),m(0x141414));mon.position.set(0,1.3,-.33);g.add(mon);
  // Glowing screen — each desk has a slightly different hue
  var scrCol=_scrColors[_scrIdx%_scrColors.length];_scrIdx++;
  var scrMat=new THREE.MeshLambertMaterial({color:scrCol,emissive:scrCol,emissiveIntensity:.85});
  var scr=new THREE.Mesh(new THREE.BoxGeometry(.56,.40,.02),scrMat);scr.position.set(0,1.3,-.31);g.add(scr);
  // Screen content (canvas label)
  var slab=document.createElement('canvas');slab.width=128;slab.height=96;
  var slc=slab.getContext('2d');
  slc.fillStyle='#010a18';slc.fillRect(0,0,128,96);
  slc.fillStyle='#1a4a80';slc.font='8px monospace';
  ['> nexus.run()','  leads: OK','  email: OK','> scanning...'].forEach(function(l,i){slc.fillText(l,6,14+i*14);});
  var slbMat=new THREE.MeshLambertMaterial({map:new THREE.CanvasTexture(slab),emissive:0x010810,emissiveIntensity:.4,transparent:true,opacity:.95});
  var slbMesh=new THREE.Mesh(new THREE.PlaneGeometry(.5,.34),slbMat);slbMesh.position.set(0,1.3,-.3);g.add(slbMesh);
  // Monitor stand
  var ms=new THREE.Mesh(new THREE.CylinderGeometry(.025,.025,.18),m(0x1a1a1a));ms.position.set(0,1.06,-.32);g.add(ms);
  var msb=new THREE.Mesh(new THREE.BoxGeometry(.22,.025,.14),m(0x1a1a1a));msb.position.set(0,.97,-.32);g.add(msb);
  // Keyboard
  var kb=new THREE.Mesh(new THREE.BoxGeometry(.48,.018,.19),new THREE.MeshLambertMaterial({color:0xd8d4cc}));kb.position.set(0,.905,.1);g.add(kb);
  // Keys grid (decorative)
  var keyMat=new THREE.MeshLambertMaterial({color:0xb0aca4});
  for(var ki=0;ki<4;ki++)for(var kj=0;kj<10;kj++){
    var key=new THREE.Mesh(new THREE.BoxGeometry(.038,.018,.036),keyMat);
    key.position.set(-.175+ki*.12,0.91+.001,.02+kj*.018-.082);g.add(key);
  }
  // Mouse
  var mouse=new THREE.Mesh(new THREE.BoxGeometry(.09,.025,.13),m(0xc8c4bc));mouse.position.set(.32,.905,.1);g.add(mouse);
  // Phone
  var ph=new THREE.Mesh(new THREE.BoxGeometry(.13,.05,.19),m(0x242424));ph.position.set(-.58,.895,-.05);g.add(ph);
  // Screen glow (small point light)
  var gl=new THREE.PointLight(scrCol,0.1,1.5);gl.position.set(0,1.3,-.25);g.add(gl);
  g.position.set(x,0,z);g.rotation.y=ry||0;scene.add(g);
  return g;
}
function mkChair(x,z,ry){
  var g=new THREE.Group();
  var s=new THREE.Mesh(new THREE.BoxGeometry(.42,.06,.42),m(0x2a2828));s.position.y=.7;g.add(s);
  var b=new THREE.Mesh(new THREE.BoxGeometry(.42,.48,.05),m(0x2a2828));b.position.set(0,.94,.18);g.add(b);
  var p2=new THREE.Mesh(new THREE.CylinderGeometry(.035,.035,.7),m(0x383030));p2.position.y=.35;g.add(p2);
  var bs=new THREE.Mesh(new THREE.CylinderGeometry(.23,.23,.04,5),m(0x282828));bs.position.y=.02;g.add(bs);
  // Armrests
  [-.22,.22].forEach(function(ax){
    var ar=new THREE.Mesh(new THREE.BoxGeometry(.04,.04,.35),m(0x383030));ar.position.set(ax,.78,0);g.add(ar);
  });
  g.position.set(x,0,z);g.rotation.y=ry||0;scene.add(g);
}

// All agent desks + chairs
Object.keys(AGPOS).forEach(function(ak){
  var p=AGPOS[ak];
  mkDesk(p.x,p.z,0);
  // Chair behind desk (towards camera from desk)
  mkChair(p.x,p.z+.8,Math.PI);
});

// Extra filing cabinets and shelves in bullpen
B(.5,1.2,.4,-3.5,.6,-3.8,0x9a9488);B(.5,1.2,.4,-3,  .6,-3.8,0x9a9488); // filing cabinets
B(.5,1.2,.4, 4.5,.6,-3.8,0x9a9488);
// Water cooler
B(.3,.8,.3,5.5,.4,-3.8,0xd0e8f8);B(.3,.12,.3,5.5,.86,-3.8,0x1868a8);
// Printer on stand
B(.6,.5,.5,5.5,.55,-.5,0xc8c4c0);B(.6,.55,.6,5.5,.275,-.5,0x8a8888);
// Plants (green cylinders)
[[4.5,4],[-5,3.5],[-13,5]].forEach(function(p){
  var pot=new THREE.Mesh(new THREE.CylinderGeometry(.2,.25,.35,8),m(0xa08860));pot.position.set(p[0],.18,p[1]);scene.add(pot);
  var plant=new THREE.Mesh(new THREE.SphereGeometry(.3,8,6),m(0x3a7028));plant.position.set(p[0],.55,p[1]);scene.add(plant);
});

// ── BREAK ROOM (right side) ───────────────────────────────────────
// x 6 to 14, z -2 to 7
// Partition wall at x=6 (partial, with opening)
B(.08,3.5,4.5,6,1.75,2.25,0xdedad0);  // wall from z=0 to 4.5
// Kitchen counter
B(2.2,.9,.55,8,.45,6.5,0x9a9488);B(2.2,.05,.55,8,.92,6.5,0xd8d4cc);
B(.8,.9,.55,10.1,.45,6.5,0x9a9488);B(.8,.05,.55,10.1,.92,6.5,0xd8d4cc);
// Fridge
B(.7,1.7,.7,7,.85,7.5,0xd8d8d8);B(.7,.05,.7,7,1.73,7.5,0xc0c0c0);
// Microwave
B(.55,.35,.4,8.7,.9,6.2,0x888888);
// Coffee maker
B(.3,.5,.3,10.1,.96,6.2,0x181818);var sm=new THREE.Mesh(new THREE.CylinderGeometry(.07,.07,.2),m(0x0a0a0a));sm.position.set(10.1,1.26,6.2);scene.add(sm);
// Break table + chairs
var bt=new THREE.Mesh(new THREE.CylinderGeometry(.7,.7,.06,8),m(0x9a7850));bt.position.set(9.5,.77,3.5);scene.add(bt);
B(.06,.77,.06,9.5,.385,3.5,0x7a6040);
[0,.7,1.4,2.1].forEach(function(a){
  var bc2=Math.cos(a*Math.PI/1.05);var bs2=Math.sin(a*Math.PI/1.05);
  mkChair(9.5+bc2*1.1,3.5+bs2*1.1,a*Math.PI/1.05+Math.PI);
});
// Vending machine
B(.8,1.8,.5,12,.9,.5,0x384830);B(.7,1.5,.35,12,.85,.32,0x1a2818);
// Break room light
pl(9.5,2.5,3.5,0xfff0d0,.3,8);
// Sign
(function(){var cv=document.createElement('canvas');cv.width=200;cv.height=40;
var c=cv.getContext('2d');c.fillStyle='rgba(240,236,228,.9)';c.fillRect(0,0,200,40);
c.font='bold 16px Arial';c.fillStyle='#6a4020';c.textAlign='center';c.fillText('Break Room',100,27);
var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv),transparent:true}));
sp.scale.set(1.8,.32,1);sp.position.set(9.5,3.3,4.8);scene.add(sp);})();

// ── ANNEX (right back) ────────────────────────────────────────────
// x 6 to 14, z -11 to -2 (HR, Finance desks)
// Already partitioned by wall at x=6 (partial) and break room partition
// Annex has standard desks at their positions (already created above)
// Extra bookshelf
B(1.5,.08,2.5,13,.5,-9.8,0x8a7048);B(1.5,.08,2.5,13,1,-9.8,0x8a7048);B(1.5,.08,2.5,13,1.5,-9.8,0x8a7048);
B(1.5,3,.08,13,1.5,-10.85,0x7a6038);
// Copier/printer
B(.9,.7,.7,11,.35,-5,0xc8c4c0);
// Annex lights
pl(10,2.5,-6,0xfff0d0,.25,7);
(function(){var cv=document.createElement('canvas');cv.width=200;cv.height=40;
var c=cv.getContext('2d');c.fillStyle='rgba(240,236,228,.9)';c.fillRect(0,0,200,40);
c.font='bold 16px Arial';c.fillStyle='#3a2060';c.textAlign='center';c.fillText('Annex',100,27);
var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv),transparent:true}));
sp.scale.set(1.5,.3,1);sp.position.set(10,3.3,-8);scene.add(sp);})();

// ── RECEPTION (front center) ──────────────────────────────────────
// Pam's curved reception desk
var rd=new THREE.Group();
var rt=new THREE.Mesh(new THREE.BoxGeometry(3,.07,1.2),m(0x9a7850));rt.position.y=.95;rd.add(rt);
var rf=new THREE.Mesh(new THREE.BoxGeometry(3,.95,.55),m(0x7a6040));rf.position.set(0,.475,.32);rd.add(rf);
// Side return
var rr=new THREE.Mesh(new THREE.BoxGeometry(.07,.95,1.2),m(0x7a6040));rr.position.set(-1.5,.475,0);rd.add(rr);
// Pam's monitor
var rpm=new THREE.Mesh(new THREE.BoxGeometry(.6,.45,.04),m(0x0a0a0a));rpm.position.set(.5,1.42,.1);rd.add(rpm);
// Nameplate
var np=new THREE.Mesh(new THREE.BoxGeometry(.5,.04,.12),m(0xc8b878));np.position.set(.5,.97,.55);rd.add(np);
rd.position.set(0,0,7.5);scene.add(rd);

// Reception area chairs (waiting area)
B(1.8,.5,.7,-4,.25,9.5,0x8888a0);B(1.8,.5,.1,-4,.25,9.15,0x7878a0); // loveseat
B(.9,.5,.7,-6,.25,9.5,0x8888a0);
// Magazine rack/table
B(.6,.05,.6,-5,.65,9,0x9a7850);B(.06,.65,.06,-5,.325,9,0x7a6040);
// Company sign on front wall
(function(){var cv=document.createElement('canvas');cv.width=400;cv.height=70;
var c=cv.getContext('2d');c.fillStyle='rgba(16,10,6,.92)';c.fillRect(0,0,400,70);
c.font='bold 32px Courier New';c.fillStyle='#e8632a';c.textAlign='center';c.fillText('⬡ NEXUS AS',200,46);
var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv),transparent:true}));
sp.scale.set(3.5,.55,1);sp.position.set(0,2.5,10.87);scene.add(sp);})();
// Lobby lights
pl(0,2.5,9,0xfff8e8,.3,7);

// ── CEILING LIGHTS (fluorescent panels) ──────────────────────────
function fluoro(x,z){
  var fi=new THREE.Mesh(new THREE.BoxGeometry(1.6,.04,.3),new THREE.MeshLambertMaterial({color:0xfffff8,emissive:0xfffff8,emissiveIntensity:.7}));
  fi.position.set(x,3.53,z);scene.add(fi);pl(x,3.2,z,0xfff8e8,.2,6);
}
[-9,-4,0,4].forEach(function(x){[-7,-3,1,5].forEach(function(z){fluoro(x,z);});});
fluoro(-11,-7.5);fluoro(9.5,-6);fluoro(9.5,3);

// ── KPI TV on back wall ───────────────────────────────────────────
B(7.5,4,.15,3,2.5,-10.88,0x080808);
var tvMesh=new THREE.Mesh(new THREE.BoxGeometry(7,.36,.04),m(0x030a03));tvMesh.position.set(3,2.5,-10.78);scene.add(tvMesh);
var tvCV=document.createElement('canvas');tvCV.width=512;tvCV.height=256;
var tvTex=new THREE.CanvasTexture(tvCV);
tvMesh.material=new THREE.MeshLambertMaterial({map:tvTex,emissive:0x001800,emissiveIntensity:.25});
tvMesh.scale.set(1,4.5/0.36,1);tvMesh.position.set(3,2.5,-10.78);
function drawTV(k){
  var c=tvCV.getContext('2d');
  // Background
  var bg=c.createLinearGradient(0,0,0,256);bg.addColorStop(0,'#020a02');bg.addColorStop(1,'#010805');
  c.fillStyle=bg;c.fillRect(0,0,512,256);
  // Scanline effect
  c.fillStyle='rgba(0,0,0,.04)';
  for(var sl=0;sl<256;sl+=2){c.fillRect(0,sl,512,1);}
  // Header
  c.fillStyle='#0a2a0a';c.fillRect(0,0,512,36);
  c.font='bold 15px Courier New';c.fillStyle='#22c55e';c.textAlign='center';
  c.fillText('⬡  NEXUS AS — LIVE KPI  ⬡',256,23);
  c.fillStyle='#22c55e44';c.fillRect(0,36,512,1);
  // Date/time
  c.font='9px Courier New';c.fillStyle='#1a5a1a';c.textAlign='right';
  c.fillText(new Date().toLocaleDateString('no-NO')+' · '+new Date().toLocaleTimeString('no-NO'),504,26);
  // KPI rows
  var rows=[
    ['📧 E-poster sendt',  k.emails_sent||0,   50,  '#60a5fa'],
    ['🎯 Leads funnet',    k.leads_found||0,   100, '#4ade80'],
    ['💰 Est. inntekt',    (k.revenue||0)+'kr',50000,'#fbbf24'],
    ['✅ Oppgaver løst',   k.tasks_done||0,    10,  '#a78bfa'],
  ];
  rows.forEach(function(r,i){
    var y=52+i*50;
    // Row bg
    c.fillStyle=i%2===0?'rgba(255,255,255,.015)':'rgba(0,0,0,.0)';c.fillRect(0,y-14,512,50);
    c.textAlign='left';c.font='11px Courier New';c.fillStyle=r[3]+'cc';c.fillText(r[0],16,y);
    c.textAlign='right';c.font='bold 14px Courier New';c.fillStyle='#e8f8e8';c.fillText(String(r[1]),504,y);
    // Progress bar background
    c.fillStyle='#0a180a';c.fillRect(16,y+8,480,7);c.strokeStyle='#1a3a1a';c.lineWidth=1;c.strokeRect(16,y+8,480,7);
    // Progress bar fill
    var n=typeof r[1]==='number'?r[1]:parseInt(String(r[1])||'0');
    var mx=r[2]>0?r[2]:1;var pct=Math.min(1,n/mx);
    var barG=c.createLinearGradient(16,0,496,0);barG.addColorStop(0,r[3]+'88');barG.addColorStop(1,r[3]+'cc');
    c.fillStyle=barG;c.fillRect(17,y+9,Math.floor(478*pct),5);
    // Percentage
    c.font='8px Courier New';c.fillStyle=r[3]+'88';c.textAlign='right';
    c.fillText(Math.round(pct*100)+'%',504,y+16);
  });
  // Goal indicator
  c.font='9px Courier New';c.fillStyle='#2a5a2a';c.textAlign='center';
  c.fillText('MÅL: 100 000 NOK  ·  Neste: '+new Date(Date.now()+18*60000).toLocaleTimeString('no-NO'),256,250);
  tvTex.needsUpdate=true;
}
drawTV(KPI);
pl(3,2.5,-9.5,0x00ff44,.1,6);

// ── HALLWAY area ──────────────────────────────────────────────────
// Stairs indicator (center-right back area, z -11 to -5, x 2 to 6)
B(4,.08,5.5,4,.04,-8,0xa8a4a0); // stair platform (lighter floor)
B(4,.06,5.5,4,.06,-8,0xb8b4b0);
// Stair treads (just decorative boxes going up)
[0,1,2,3].forEach(function(i){B(3.5,.06,1.2,4,(i+1)*.18,-(8+i*.5-.9),0xb0aca8);});
// Staircase sign
(function(){var cv=document.createElement('canvas');cv.width=160;cv.height=36;
var c=cv.getContext('2d');c.fillStyle='rgba(240,236,228,.9)';c.fillRect(0,0,160,36);
c.font='13px Arial';c.fillStyle='#606058';c.textAlign='center';c.fillText('Stairs ↑',80,24);
var sp=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(cv),transparent:true}));
sp.scale.set(1.2,.27,1);sp.position.set(4,3.2,-10);scene.add(sp);})();

// ── AVATARS ───────────────────────────────────────────────────────
function mkFace(skin,charName){
  var cv=document.createElement('canvas');cv.width=256;cv.height=256;
  var c=cv.getContext('2d');
  // Face base with gradient
  var fg=c.createRadialGradient(110,100,10,128,128,110);
  fg.addColorStop(0,skin);fg.addColorStop(1,shadeHex(skin,-20));
  c.fillStyle=fg;c.beginPath();c.ellipse(128,128,110,118,0,0,Math.PI*2);c.fill();
  // Jawline definition
  var jg=c.createRadialGradient(128,200,20,128,128,110);
  jg.addColorStop(0,'rgba(0,0,0,.08)');jg.addColorStop(1,'rgba(0,0,0,0)');
  c.fillStyle=jg;c.fillRect(0,0,256,256);
  // Cheek highlights
  c.fillStyle='rgba(255,220,200,.1)';
  c.beginPath();c.ellipse(82,150,22,16,-.3,0,Math.PI*2);c.fill();
  c.beginPath();c.ellipse(174,150,22,16,.3,0,Math.PI*2);c.fill();
  // Eye whites
  c.fillStyle='#fff';
  c.beginPath();c.ellipse(82,108,20,13,-.08,0,Math.PI*2);c.fill();
  c.beginPath();c.ellipse(174,108,20,13,.08,0,Math.PI*2);c.fill();
  // Iris
  c.fillStyle='#2a1a08';
  c.beginPath();c.arc(84,110,10,0,Math.PI*2);c.fill();
  c.beginPath();c.arc(176,110,10,0,Math.PI*2);c.fill();
  // Iris color ring
  c.fillStyle='rgba(60,100,160,.5)';
  c.beginPath();c.arc(84,110,8,0,Math.PI*2);c.fill();
  c.beginPath();c.arc(176,110,8,0,Math.PI*2);c.fill();
  // Pupils
  c.fillStyle='#0a0806';
  c.beginPath();c.arc(84,110,5,0,Math.PI*2);c.fill();
  c.beginPath();c.arc(176,110,5,0,Math.PI*2);c.fill();
  // Eye shine
  c.fillStyle='rgba(255,255,255,.85)';
  c.beginPath();c.arc(87,107,3,0,Math.PI*2);c.fill();
  c.beginPath();c.arc(179,107,3,0,Math.PI*2);c.fill();
  // Eyebrows (slight arch, character-dependent)
  c.strokeStyle='#2a1408';c.lineWidth=4;c.lineCap='round';
  c.beginPath();c.moveTo(60,84);c.quadraticCurveTo(82,74,106,82);c.stroke();
  c.beginPath();c.moveTo(150,82);c.quadraticCurveTo(174,74,196,84);c.stroke();
  // Nose bridge + tip
  c.strokeStyle=shadeHex(skin,-30);c.lineWidth=2.5;c.lineCap='round';
  c.beginPath();c.moveTo(122,120);c.quadraticCurveTo(116,148,120,158);c.quadraticCurveTo(128,164,136,158);c.stroke();
  // Nostrils
  c.fillStyle=shadeHex(skin,-25);
  c.beginPath();c.ellipse(116,160,7,4.5,.2,0,Math.PI*2);c.fill();
  c.beginPath();c.ellipse(140,160,7,4.5,-.2,0,Math.PI*2);c.fill();
  // Mouth — smile
  c.strokeStyle='#7a3018';c.lineWidth=5;c.lineCap='round';
  c.beginPath();c.moveTo(100,188);c.quadraticCurveTo(128,204,156,188);c.stroke();
  // Lips
  c.fillStyle=shadeHex(skin,-15);
  c.beginPath();c.ellipse(128,185,28,8,0,0,Math.PI*2);c.fill();
  // Chin dimple
  c.fillStyle='rgba(0,0,0,.05)';
  c.beginPath();c.ellipse(128,220,12,8,0,0,Math.PI*2);c.fill();
  return new THREE.CanvasTexture(cv);
}
function shadeHex(hex,amount){
  var c=parseInt(hex.replace('#',''),16);
  var r=Math.max(0,Math.min(255,((c>>16)&0xff)+amount));
  var g=Math.max(0,Math.min(255,((c>>8)&0xff)+amount));
  var b=Math.max(0,Math.min(255,(c&0xff)+amount));
  return 'rgb('+r+','+g+','+b+')';
}

var agMs={};
var bubIds={};
Object.keys(AGENTS).forEach(function(ak){bubIds[ak]='b_'+ak;});
var bubTxt={};Object.keys(AGENTS).forEach(function(k){bubTxt[k]='';});

function mkAvatar(ak,x,z){
  var ag=AGENTS[ak];if(!ag)return;
  var g=new THREE.Group();
  var sc=parseInt((ag.skin||'#c8a070').replace('#',''),16);
  var hc=ag.hair||0x1a0e08;
  var bc=ag.shirt||0x3a5070;
  var pc=ag.pants||0x282828;
  var isFemale=!!ag.female;
  var isTall=!!ag.tall;
  var bodyH=isTall?0.60:0.54;
  var torsoH=isTall?0.64:0.58;

  // Shoes (more detailed)
  [-.12,.12].forEach(function(sx){
    var sh=new THREE.Mesh(new THREE.BoxGeometry(.13,.085,.24),m(0x0a0806));sh.position.set(sx,.042,.04);g.add(sh);
    // Sole
    var sole=new THREE.Mesh(new THREE.BoxGeometry(.135,.02,.25),m(0x181410));sole.position.set(sx,.01,.04);g.add(sole);
  });
  // Legs — tapered
  [-.12,.12].forEach(function(lx){
    var l=new THREE.Mesh(new THREE.CylinderGeometry(.073,.083,bodyH,8),m(pc));
    l.position.set(lx,bodyH/2+.09,0);g.add(l);
  });
  // Belt
  var belt=new THREE.Mesh(new THREE.BoxGeometry(.40,.035,.26),m(0x0a0806));
  belt.position.set(0,bodyH+.09,0);g.add(belt);
  var buckle=new THREE.Mesh(new THREE.BoxGeometry(.06,.04,.02),m(0xc8a828));
  buckle.position.set(0,bodyH+.09,.14);g.add(buckle);

  // Torso / jacket
  var body=new THREE.Mesh(new THREE.BoxGeometry(isFemale?.44:.48,torsoH,.30),m(bc));
  body.position.y=bodyH+.09+torsoH/2;g.add(body);
  if(!isFemale){
    // Jacket lapels
    var lapL=new THREE.Mesh(new THREE.BoxGeometry(.09,.3,.05),m(Math.max(0,bc-0x181818)));
    lapL.position.set(-.12,bodyH+.09+torsoH*.65,.16);lapL.rotation.z=-.3;g.add(lapL);
    var lapR=new THREE.Mesh(new THREE.BoxGeometry(.09,.3,.05),m(Math.max(0,bc-0x181818)));
    lapR.position.set(.12,bodyH+.09+torsoH*.65,.16);lapR.rotation.z=.3;g.add(lapR);
    // Shirt visible (white strip)
    var shirt=new THREE.Mesh(new THREE.BoxGeometry(.12,torsoH*.7,.02),m(0xf4f0e8));
    shirt.position.set(0,bodyH+.09+torsoH*.35,.16);g.add(shirt);
    // Tie
    var tieCol=(hc===0x3a2010)?0x8a1818:(hc===0x1a0e08)?0x4a2808:hc;
    var tie=new THREE.Mesh(new THREE.BoxGeometry(.055,.38,.02),m(tieCol));
    tie.position.set(.015,bodyH+.09+torsoH*.36,.17);g.add(tie);
    var tieknot=new THREE.Mesh(new THREE.BoxGeometry(.06,.055,.025),m(tieCol));
    tieknot.position.set(.015,bodyH+.09+torsoH*.72,.17);g.add(tieknot);
  } else {
    // Female: collar / scarf
    var scarf=new THREE.Mesh(new THREE.TorusGeometry(.09,.025,6,8),m(hc));
    scarf.rotation.x=Math.PI/2;scarf.position.set(0,bodyH+.09+torsoH+.04,0);g.add(scarf);
  }

  // Collar
  var col=new THREE.Mesh(new THREE.BoxGeometry(.46,.055,.30),m(0xf0ece4));
  col.position.set(0,bodyH+.09+torsoH-.02,0);g.add(col);

  // Arms with elbows (upper + lower)
  var armRefs=[];
  [-.28,.28].forEach(function(ax,ai){
    var upper=new THREE.Mesh(new THREE.CylinderGeometry(.068,.075,.26,7),m(bc));
    upper.position.set(ax,bodyH+.09+torsoH*.72,0);upper.rotation.z=ax>0?-.12:.12;g.add(upper);
    var elbow=new THREE.Mesh(new THREE.SphereGeometry(.072,7,5),m(bc));
    elbow.position.set(ax,bodyH+.09+torsoH*.52,0);g.add(elbow);
    var lower=new THREE.Mesh(new THREE.CylinderGeometry(.063,.068,.22,7),m(bc));
    lower.position.set(ax,bodyH+.09+torsoH*.38,0);lower.rotation.z=ax>0?-.12:.12;g.add(lower);
    var hand=new THREE.Mesh(new THREE.SphereGeometry(.073,8,6),m(sc));
    hand.position.set(ax,bodyH+.09+torsoH*.24,0);g.add(hand);
    armRefs.push({upper:upper,elbow:elbow,lower:lower,hand:hand,side:ax>0?1:-1});
  });

  // Neck
  var nk=new THREE.Mesh(new THREE.CylinderGeometry(.075,.095,.15,8),m(sc));
  nk.position.y=bodyH+.09+torsoH+.07;g.add(nk);

  // Head — better geometry
  var hdMat=new THREE.MeshLambertMaterial({map:mkFace('#'+(sc).toString(16).padStart(6,'0'),ag.char)});
  var hd=new THREE.Mesh(new THREE.SphereGeometry(.245,18,14),hdMat);
  hd.scale.set(1,.98,1);hd.position.y=bodyH+.09+torsoH+.33;g.add(hd);

  // Hair
  var hairPhi=isFemale?.62:.50;
  var hr=new THREE.Mesh(new THREE.SphereGeometry(.25,16,10,0,Math.PI*2,0,Math.PI*hairPhi),m(hc));
  hr.position.y=bodyH+.09+torsoH+.38;hr.rotation.x=.12;g.add(hr);
  if(isFemale){
    // Long hair sides
    var hrL=new THREE.Mesh(new THREE.CylinderGeometry(.06,.1,.3,7),m(hc));
    hrL.position.set(-.18,bodyH+.09+torsoH+.2,-.05);hrL.rotation.z=.2;g.add(hrL);
    var hrR=new THREE.Mesh(new THREE.CylinderGeometry(.06,.1,.3,7),m(hc));
    hrR.position.set(.18,bodyH+.09+torsoH+.2,-.05);hrR.rotation.z=-.2;g.add(hrR);
    var hrB=new THREE.Mesh(new THREE.CylinderGeometry(.12,.18,.28,8),m(hc));
    hrB.position.set(0,bodyH+.09+torsoH+.14,-.12);g.add(hrB);
  }

  // Ears
  var eY=bodyH+.09+torsoH+.31;
  [-.255,.255].forEach(function(ex){
    var e=new THREE.Mesh(new THREE.SphereGeometry(.06,7,5),m(sc));
    e.position.set(ex,eY,0);g.add(e);
  });

  // Glasses
  if(ag.glasses){
    var gfr=new THREE.Mesh(new THREE.TorusGeometry(.065,.008,6,12),m(0x181010));
    gfr.rotation.y=Math.PI/2;gfr.position.set(-.11,eY+.04,.23);g.add(gfr);
    var gfrR=new THREE.Mesh(new THREE.TorusGeometry(.065,.008,6,12),m(0x181010));
    gfrR.rotation.y=Math.PI/2;gfrR.position.set(.11,eY+.04,.23);g.add(gfrR);
    var gbr=new THREE.Mesh(new THREE.BoxGeometry(.24,.01,.01),m(0x181010));
    gbr.position.set(0,eY+.07,.23);g.add(gbr);
    [-.19,.19].forEach(function(tx){
      var tt=new THREE.Mesh(new THREE.BoxGeometry(.08,.008,.008),m(0x181010));
      tt.position.set(tx,eY+.04,.16);tt.rotation.y=Math.PI/2;g.add(tt);
    });
  }

  // Name label (larger, two-line: name + role)
  var lc=document.createElement('canvas');lc.width=256;lc.height=56;
  var lctx=lc.getContext('2d');
  lctx.fillStyle='rgba(8,4,2,.88)';
  lctx.roundRect?lctx.roundRect(0,0,256,56,8):lctx.fillRect(0,0,256,56);
  lctx.fill();
  lctx.font='bold 20px Courier New';lctx.fillStyle=ag.color;lctx.textAlign='center';
  lctx.fillText(ag.name,128,24);
  lctx.font='11px Courier New';lctx.fillStyle='rgba(180,140,100,.7)';
  lctx.fillText(ag.char+' · '+ag.role.slice(0,22),128,44);
  var lbl=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(lc),transparent:true}));
  lbl.scale.set(1.7,.38,1);lbl.position.set(0,bodyH+.09+torsoH+1.0,0);g.add(lbl);

  var totalH=bodyH+.09+torsoH;
  g.position.set(x,0,z);scene.add(g);
  agMs[ak]={g:g,x:x,z:z,tx:x,tz:z,bob:Math.random()*Math.PI*2,bh:totalH,arms:armRefs};
}

Object.keys(AGENTS).forEach(function(ak){
  var p=AGPOS[ak];if(p)mkAvatar(ak,p.x,p.z);
});

// Nicholas avatar (only when online) — Michael Scott's office chair
var nickG=null;
function mkNick(){
  var g=new THREE.Group();
  var bc=parseInt(U_COLOR.replace('#',''),16)||0xe8632a;
  // Legs
  [-.11,.11].forEach(function(lx){
    var l=new THREE.Mesh(new THREE.CylinderGeometry(.075,.085,.56),m(0x282828));
    l.position.set(lx,.37,0);g.add(l);
  });
  var body=new THREE.Mesh(new THREE.BoxGeometry(.46,.6,.28),m(bc));body.position.y=.94;g.add(body);
  // White shirt collar
  var col2=new THREE.Mesh(new THREE.BoxGeometry(.48,.06,.3),m(0xf0ece4));col2.position.set(0,1.24,0);g.add(col2);
  // Head
  var hd=new THREE.Mesh(new THREE.SphereGeometry(.235,14,12),new THREE.MeshLambertMaterial({map:mkFace('#c8a070','Michael')}));
  hd.position.y=1.6;g.add(hd);
  var hr=new THREE.Mesh(new THREE.SphereGeometry(.24,14,9,0,Math.PI*2,0,Math.PI*.48),m(0x2a1a0a));
  hr.position.y=1.66;hr.rotation.x=.1;g.add(hr);
  [-.25,.25].forEach(function(ex){
    var e=new THREE.Mesh(new THREE.SphereGeometry(.055,7,5),m(0xc8a070));e.position.set(ex,1.58,0);g.add(e);
  });
  // Name label
  var lc=document.createElement('canvas');lc.width=240;lc.height=44;
  var lctx=lc.getContext('2d');lctx.fillStyle='rgba(12,7,4,.92)';lctx.fillRect(0,0,240,44);
  lctx.font='bold 18px Courier New';lctx.fillStyle='#e8632a';lctx.textAlign='center';
  lctx.fillText('⭐ '+U_NAME,120,30);
  var lbl=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(lc),transparent:true}));
  lbl.scale.set(1.6,.33,1);lbl.position.set(0,2.08,0);g.add(lbl);
  g.position.set(-11,0,-7.8); // Michael's desk
  scene.add(g); return g;
}
nickG=mkNick();

// ── CAMERA ────────────────────────────────────────────────────────
// Default: isometric overview (like floor plan, no ceiling)
var walkMode=false,plocked=false;
var euler=new THREE.Euler(0,0,0,'YXZ');
var vel=new THREE.Vector3();
var keys={};

// Isometric overview camera
function overviewCam(){
  camera.position.set(0,20,8);
  camera.lookAt(0,0,-1);
}
overviewCam();

// For orbit (small adjustments in overview)
var cToff=0,cPoff=0;
var drag=false,prev={x:0,y:0};
var cv3=document.getElementById('c');
cv3.addEventListener('mousedown',function(e){if(!walkMode){drag=true;prev={x:e.clientX,y:e.clientY};}});
addEventListener('mouseup',function(){drag=false;});
addEventListener('mousemove',function(e){
  if(drag&&!walkMode){
    cToff-=(e.clientX-prev.x)*.003;
    cPoff=Math.max(-.3,Math.min(.3,cPoff-(e.clientY-prev.y)*.003));
    prev={x:e.clientX,y:e.clientY};
    camera.position.set(cToff*10,20+cPoff*5,8-cPoff*3);
    camera.lookAt(cToff*5,0,-1);
  }
  if(plocked){
    euler.y-=e.movementX*.0025;
    euler.x=Math.max(-1.1,Math.min(.4,euler.x-e.movementY*.0025));
    camera.quaternion.setFromEuler(euler);
  }
});
cv3.addEventListener('wheel',function(e){
  if(!walkMode){
    var d=e.deltaY*.015;
    camera.position.y=Math.max(8,Math.min(28,camera.position.y+d));
    camera.position.z=Math.max(4,Math.min(14,camera.position.z+d*.35));
    camera.lookAt(cToff*5,0,-1);
  }
});

function toggleWalk(){
  walkMode=!walkMode;
  var btn=document.getElementById('wb');
  if(walkMode){
    btn.textContent='🚶 GÅ PÅ';btn.classList.add('on');
    document.getElementById('wui').style.display='flex';
    document.getElementById('mlhint').style.display='block';
    document.getElementById('mm').style.display='block';
    document.getElementById('statsbar').style.display='block';
    loadLiveStats();
    ceilMesh.visible=true;
    scene.fog.near=12;scene.fog.far=32;
    camera.fov=70;camera.updateProjectionMatrix();
    // Start position: bullpen center, facing into office (toward -z)
    camera.position.set(0,1.7,5);
    euler.set(0,0,0);camera.quaternion.setFromEuler(euler);
    vel.set(0,0,0);
  }else{
    btn.textContent='🚶 Gå (F)';btn.classList.remove('on');
    document.getElementById('wui').style.display='none';
    document.getElementById('mlhint').style.display='none';
    document.getElementById('mm').style.display='none';
    document.getElementById('statsbar').style.display='none';
    document.getElementById('vtip').style.display='none';
    document.getElementById('agpop').style.display='none';
    ceilMesh.visible=false;
    scene.fog.near=25;scene.fog.far=50;
    camera.fov=60;camera.updateProjectionMatrix();
    if(plocked){document.exitPointerLock();plocked=false;}
    cToff=0;cPoff=0;overviewCam();
    stopMic();
  }
}
// CRITICAL: Never auto-exit walk mode on pointer lock change
// Walk mode stays active — pointer lock only controls mouse look
addEventListener('pointerlockchange',function(){
  plocked=!!document.pointerLockElement;
  var hint=document.getElementById('mlhint');
  if(hint)hint.style.display=(walkMode&&!plocked)?'block':'none';
});
addEventListener('keydown',function(e){
  keys[e.code]=true;
  if(e.code==='KeyF')toggleWalk();
  if(e.code==='KeyV')toggleMic();
  if(e.code==='Escape'&&walkMode)toggleWalk();
  // E key = focus chat input (walk mode)
  if(e.code==='KeyE'&&walkMode){
    var ci=document.getElementById('wci');if(ci){ci.focus();e.preventDefault();}
  }
  // Enter = send chat if input focused
  if(e.code==='Enter'&&walkMode&&document.activeElement===document.getElementById('wci')){
    sendChat();e.preventDefault();
  }
});
addEventListener('keyup',function(e){keys[e.code]=false;});
cv3.addEventListener('click',function(){if(walkMode&&!plocked)cv3.requestPointerLock();});

// ── VOICE CHAT ────────────────────────────────────────────────────
var recognition=null,micOn=false;
(function(){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(SR){recognition=new SR();recognition.lang='nb-NO';recognition.continuous=false;recognition.interimResults=false;
    recognition.onresult=function(ev){
      var txt=ev.results[0][0].transcript;
      stopMic();processVoice(txt);
    };
    recognition.onerror=function(){stopMic();};
    recognition.onend=function(){if(micOn)stopMic();};
  }
})();

function toggleMic(){
  if(!recognition){toast('Nettleseren støtter ikke talegjenkjenning',3000);return;}
  if(micOn)stopMic();else startMic();
}
function startMic(){
  micOn=true;
  var mb=document.getElementById('mic-btn');mb.textContent='🎤 Lytter...';mb.classList.add('listening');
  var vtip=document.getElementById('vtip');vtip.textContent='🎤 Lytter... si noe!';vtip.style.display='block';
  try{recognition.start();}catch(e){stopMic();}
}
function stopMic(){
  micOn=false;
  var mb=document.getElementById('mic-btn');mb.textContent='🎤 Snakk';mb.classList.remove('listening');
  document.getElementById('vtip').style.display='none';
  try{recognition.stop();}catch(e){}
}

// Find agents near camera (in walk mode)
function nearbyAgents(radius){
  var near=[];
  Object.keys(agMs).forEach(function(ak){
    var a=agMs[ak];
    var dx=a.x-camera.position.x,dz=a.z-camera.position.z;
    var dist=Math.sqrt(dx*dx+dz*dz);
    if(dist<(radius||8))near.push({ak:ak,dist:dist});
  });
  near.sort(function(a,b){return a.dist-b.dist;});
  return near.slice(0,5).map(function(x){return x.ak;});
}

async function processVoice(text){
  document.getElementById('ll').textContent='Du: '+text.slice(0,50);
  var near=walkMode?nearbyAgents(8):Object.keys(AGENTS).slice(0,4);
  try{
    var resp=await fetch('/api/voice',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:text,agents:near})});
    var data=await resp.json();
    if(data.responses&&data.responses.length){
      data.responses.forEach(function(r,i){
        setTimeout(function(){
          showBub(r.agent,r.text,9000);
          speakText(r.text,r.pitch||1,r.rate||1);
        },i*1800);
      });
    }
  }catch(e){console.log('Voice error',e);}
}

function sendChat(){
  var inp=document.getElementById('wci');
  var text=(inp&&inp.value||'').trim();
  if(!text)return;
  inp.value='';
  processVoice(text);
}

// ── Live stats from integration bridge ────────────────────────────
async function loadLiveStats(){
  try{
    var r=await fetch('/api/nexus/stats');
    if(!r.ok)return;
    var d=await r.json();
    var sl=document.getElementById('s-leads');
    var se=document.getElementById('s-email');
    var sr=document.getElementById('s-rev');
    if(sl)sl.textContent=d.leads_total||0;
    if(se)se.textContent=d.emails_sent||0;
    if(sr)sr.textContent=(d.revenue_est||0).toLocaleString('no-NO');
    // Update KPI TV
    drawTV({leads_found:d.leads_total,emails_sent:d.emails_sent,revenue:d.revenue_est,tasks_done:0});
  }catch(e){}
}
// Refresh live stats every 3 min
setInterval(loadLiveStats,180000);
loadLiveStats();

// Speech synthesis
var synth=window.speechSynthesis;
var synthVoice=null;
if(synth){
  function loadVoices(){
    var vs=synth.getVoices();
    synthVoice=vs.find(function(v){return v.lang==='nb-NO';})||
               vs.find(function(v){return v.lang.startsWith('no');})||
               vs.find(function(v){return v.lang.startsWith('en');})||null;
  }
  loadVoices();
  if(synth.onvoiceschanged!==undefined)synth.onvoiceschanged=loadVoices;
}
function speakText(text,pitch,rate){
  if(!synth)return;
  var ut=new SpeechSynthesisUtterance(text);
  if(synthVoice)ut.voice=synthVoice;
  ut.pitch=pitch||1;ut.rate=rate||1;ut.volume=.85;
  synth.speak(ut);
}

// ── AGENT RANDOM IDLE CHATTER ─────────────────────────────────────
var IDLE={
  nexus:   ['Analyserer 23 nye leads...','Pitch-optimalisering pågår','Reply rate: 8.4% — over snitt!','Ny lead fra Apollo: CEO i Bergen','Kampanje ytelse: ↑12% denne uken','Sender kald-epost nå...'],
  jordan:  ['Faktum: disiplin = inntekt','Koordinerer alle 12 agenter','Strategi-oppdatering sendt til NEXUS','Sjekker MCP-board for meldinger','Produktivitetsrapport: 94% effektivitet','Planlegger Q2-kampanje'],
  pam:     ['God morgen! Kaffe er klart ☕','Møte om 10 min i konferanserommet','Jeg har booket Nicholas sine avtaler','Ny melding fra klient — videresender','Påminnelse: rapport forfaller fredag','Smiley har sluttet... igjen'],
  jim_ai:  ['Koden merger grønt! ✅','Lager ny salgsfunnel nå','PR #47 godkjent 🎉','Sprint-demo klar til fredag','Unit-tester: 98% coverage','Fikk positiv respons fra lead!'],
  dwight_ai:['Stack oppdatert til nyeste versjon','Faktum: automatisering sparer 40t/uke','Scaler infrastruktur nå','Ny modul ferdig deployet','API-integrasjon validert','Identity theft is not a joke — men koden er det'],
  angela:  ['HR-policy oppdatert','Alle møter dokumentert ✓','Ingen overtidsslurv denne uken','Regelverket er tydelig for alle','Kvalitetssikring: bestått','Ny onboarding-guide ferdig'],
  oscar:   ['API-kostnad: $2.14 — under budsjett 💚','Revenue YTD oppdatert','Stripe webhook validert','Burn rate: optimal','Analyserer kostnad per lead','Skattemelding... neste kvartal'],
  leonardo:['Ny systemarkitektur skissert','Elegant løsning identifisert','Microservice refaktorert','Database-skjema optimalisert','API-design ferdig reviewet','Arkitektur: skjønnhet + funksjon'],
  albert:  ['Enkelt sett: O(log n) er nok','Algoritmen konvergerer 37% raskere','Bevist: løsningen er optimal','Matematikken stemmer — som alltid','Relativt sett... dette er trivielt','Beregning ferdig. Drikker kaffe.'],
  ada:     ['Koden er ren og lesbar ✨','Refaktorert 3 funksjoner til én','Alle tester grønne!','Dokumentasjon oppdatert','Pattern: observer implementert','Koden snakker for seg selv'],
  nikola:  ['Resonansfrekvens: 432Hz — perfekt','Energioverføring uten tap!','Det nye systemet oscillerer fint','Prototype: stabil og skalerbar','Strøm uten motstand = profitt','Fremtiden er trådløs og autonom'],
  meredith:['Markedsdata: lastet og analysert','Kilde funnet: Harvard Business Review','Kompetitor-analyse ferdig','Ny innsikt: SMB-segmentet vokser 18%','Rapport sendt til NEXUS','Data lyver aldri — folk lyver'],
};
function randomIdle(){
  var aks=Object.keys(agMs);
  var ak=aks[Math.floor(Math.random()*aks.length)];
  var lines=IDLE[ak];
  if(lines)showBub(ak,lines[Math.floor(Math.random()*lines.length)],5000);
  setTimeout(randomIdle,5000+Math.random()*7000);
}
setTimeout(randomIdle,4000);

// ── SPEECH BUBBLES ────────────────────────────────────────────────
function showBub(ak,text,dur){
  var elid=bubIds[ak];if(!elid)return;
  bubTxt[ak]=text;
  var el=document.getElementById(elid);if(!el)return;
  el.textContent=text;clearTimeout(el._t);
  el._t=setTimeout(function(){bubTxt[ak]='';el.style.display='none';},dur||6000);
  var ag=AGENTS[ak];
  document.getElementById('ll').textContent=(ag&&ag.name||ak.toUpperCase())+' — '+text.slice(0,50);
}
function updateBubs(){
  Object.keys(agMs).forEach(function(ak){
    var a=agMs[ak];var elid=bubIds[ak];
    if(!a||!elid||!bubTxt[ak])return;
    var v=new THREE.Vector3(a.x,a.bh+1.2,a.z).project(camera);
    var bw=innerWidth,bh=innerHeight-80;
    var sx=(v.x*.5+.5)*bw,sy=(-.5*v.y+.5)*bh+44;
    var el=document.getElementById(elid);
    if(el&&v.z<1&&v.z>-1&&sx>10&&sx<bw-10&&sy>52&&sy<bh+30){
      el.style.left=sx+'px';el.style.top=(sy-4)+'px';el.style.display='block';
    }else if(el)el.style.display='none';
  });
}

// ── PANEL ─────────────────────────────────────────────────────────
var atab='tasks',popen=false;
var tasks=TASKS.slice(),ideas=IDEAS.slice(),feed=FEED.slice(0,50);
function openP(tab){
  if(popen&&atab===tab){popen=false;document.getElementById('panel').classList.remove('open');return;}
  popen=true;document.getElementById('panel').classList.add('open');showTab(tab);
}
function showTab(t){
  atab=t;
  document.querySelectorAll('.ptab').forEach(function(x){x.classList.remove('on');});
  var el=document.getElementById('tab-'+t);if(el)el.classList.add('on');
  document.getElementById('tform').style.display=t==='tasks'?'block':'none';
  renderP();
}
function renderP(){
  var el=document.getElementById('pc');
  if(atab==='tasks'){
    var open=tasks.filter(function(t){return t.status!=='done';});
    el.innerHTML=open.length?open.map(function(t){return(
      '<div class=tc onclick="cycleTask('+t.id+')">'+
      '<div class=th2><span class="bx '+(t.status==='pending'?'bp':t.status==='in_progress'?'bi':'bdone')+'">'+t.status.replace('_',' ')+'</span>'+
      '<span class="bx ball">'+t.assigned_to+'</span></div>'+
      '<div class=tt2>'+t.title+'</div>'+
      '<div class=tm2>'+t.posted_by+' · '+(t.created_at||'').slice(0,16)+'</div></div>'
    );}).join(''):'<div style="color:#3a2010;padding:14px;font-size:10px">Ingen åpne oppgaver</div>';
  }else if(atab==='ideas'){
    el.innerHTML=ideas.length?ideas.map(function(i){return(
      '<div class=ic><div class=ia>'+(AGENTS[i.agent]&&AGENTS[i.agent].char||'AI')+' · '+i.category+'</div>'+
      '<div class=it>'+i.idea+'</div><div class=tm2>'+(i.created_at||'').slice(0,16)+'</div></div>'
    );}).join(''):'<div style="color:#3a2010;padding:14px;font-size:10px">Ingen ideer enda</div>';
  }else if(atab==='feed'){
    el.innerHTML=feed.length?feed.map(function(a){return(
      '<div class=fi2><div class=fd2 style="background:'+(AGENTS[a.agent]&&AGENTS[a.agent].color||'#888')+'"></div>'+
      '<div class=ft2><b style="color:'+(AGENTS[a.agent]&&AGENTS[a.agent].color||'#888')+'">'+(a.agent||'').toUpperCase()+'</b> — '+a.activity+'</div>'+
      '<div class=ftm2>'+(a.created_at||'').slice(11,16)+'</div></div>'
    );}).join(''):'<div style="color:#3a2010;padding:14px;font-size:10px">Ingen aktivitet</div>';
  }else{
    el.innerHTML=USERS.map(function(u){return(
      '<div class=pr2><div class=pav2 style="background:'+(u.role==='admin'?'#7c3aed':'#0e7490')+'">'+(u.display_name||u.username)[0].toUpperCase()+'</div>'+
      '<div><div class=pn2>'+(u.display_name||u.username)+' '+(u.role==='admin'?'👑':'')+'</div>'+
      '<div class=prole2>'+u.role+' · '+(u.last_seen||'').slice(0,16)+'</div></div></div>'
    );}).join('');
  }
}
function cycleTask(id){
  var ord=['pending','in_progress','done'];
  var t=tasks.find(function(x){return x.id===id;});if(!t)return;
  var nx=ord[(ord.indexOf(t.status)+1)%ord.length];
  fetch('/api/tasks/'+id+'/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status:nx})});
  t.status=nx;renderP();
}
async function postTask(){
  var title=document.getElementById('nt').value.trim();
  var ag=document.getElementById('ta').value;
  if(!title)return;
  document.querySelector('#tform button').textContent='Sender...';
  await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title,assigned_to:ag,priority:1})});
  // Also notify Jordan
  if(ag==='all'||ag==='jordan'){
    fetch('/api/trigger/jordan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:title})}).catch(function(){});
  }
  document.getElementById('nt').value='';
  document.querySelector('#tform button').textContent='SEND OPPGAVE ▶';
  toast('✅ Sendt! Agentene går til konferanserom — sjekk Telegram 📱');
  // Reload stats after task
  setTimeout(loadLiveStats,8000);
}
function toast(msg,dur){
  var t=document.getElementById('toast');t.textContent=msg;t.classList.add('on');
  setTimeout(function(){t.classList.remove('on');},dur||3500);
}
renderP();

// ── SSE ───────────────────────────────────────────────────────────
var es=new EventSource('/api/stream');
es.onmessage=function(ev){
  var d=JSON.parse(ev.data);if(d.type==='ping')return;
  if(d.type==='new_task'){tasks.unshift(d.task);if(atab==='tasks')renderP();toast('📋 '+d.task.title);}
  if(d.type==='task_update'){var t2=tasks.find(function(x){return x.id===d.id;});if(t2){t2.status=d.status;if(atab==='tasks')renderP();}}
  if(d.type==='agent_move'){var am=agMs[d.agent];if(am){am.tx=d.x;am.tz=d.z;}if(d.text)showBub(d.agent,d.text,4000);}
  if(d.type==='agent_chat'){showBub(d.agent,d.text,9000);speakText(d.text,AGENTS[d.agent]&&AGENTS[d.agent].pitch||1,AGENTS[d.agent]&&AGENTS[d.agent].rate||1);}
  if(d.type==='activity'){
    feed.unshift(Object.assign({},d,{created_at:new Date().toISOString()}));feed=feed.slice(0,50);
    showBub(d.agent,d.activity.slice(0,70));if(atab==='feed')renderP();
  }
  if(d.type==='new_idea'){ideas.unshift(d.idea);if(atab==='ideas')renderP();toast('💡 '+d.idea.idea.slice(0,40));}
  if(d.type==='kpi'){drawTV(d.data);}
};

// ── RADIO ─────────────────────────────────────────────────────────
var ron=false;
function toggleRadio(){
  ron=!ron;var a=document.getElementById('ra'),b=document.getElementById('rb');
  if(ron){a.play().catch(function(){});b.textContent='⏸ Pause';}
  else{a.pause();b.textContent='▶ Radio';}
}

// ── ANIMATE ───────────────────────────────────────────────────────
var clock=new THREE.Clock();
var vel=new THREE.Vector3();
var walkBob=0,bobT=0,isMoving=false;
var lastArea='';

function animate(){
  requestAnimationFrame(animate);
  var dt=Math.min(clock.getDelta(),.05);
  var t=clock.getElapsedTime();

  // ── Agent movement, bob, typing, face-turning ──────────────────
  Object.keys(agMs).forEach(function(ak){
    var a=agMs[ak];
    a.x+=(a.tx-a.x)*.06;
    a.z+=(a.tz-a.z)*.06;
    var moving=Math.abs(a.tx-a.x)+Math.abs(a.tz-a.z)>.08;
    var bobY=Math.sin(t*(moving?3:1.1)+a.bob)*(moving?.025:.01);
    a.g.position.set(a.x,bobY,a.z);
    if(moving){
      a.g.rotation.y=Math.atan2(a.tx-a.x,a.tz-a.z);
    } else if(walkMode){
      var dx=camera.position.x-a.x,dz=camera.position.z-a.z;
      if(Math.sqrt(dx*dx+dz*dz)<4.5)
        a.g.rotation.y+=(Math.atan2(dx,dz)-a.g.rotation.y)*.1;
    }
    // Typing animation — arms angle toward keyboard when at desk
    if(!moving&&a.arms){
      var typeAmt=Math.sin(t*4.5+a.bob)*.12; // subtle arm oscillation
      a.arms.forEach(function(arm){
        arm.upper.rotation.z=arm.side*(-.08+typeAmt*.05);
        arm.lower.rotation.z=arm.side*(-.25+typeAmt*.12);
        arm.hand.position.y=arm.hand.position.y; // keep position
      });
    }
  });

  // Nick — hidden in walk mode (player IS the camera)
  if(nickG)nickG.visible=!walkMode;

  // ── Walk mode ──────────────────────────────────────────────────
  if(walkMode){
    var sprint=keys['ShiftLeft']||keys['ShiftRight'];
    var speed=(sprint?0.22:0.13)*60*dt;
    var fwd=new THREE.Vector3(
      -Math.sin(euler.y)*Math.cos(euler.x),
      -Math.sin(euler.x),
      -Math.cos(euler.y)*Math.cos(euler.x));
    var rgt=new THREE.Vector3().crossVectors(fwd,new THREE.Vector3(0,1,0)).normalize();
    var acc=new THREE.Vector3();
    if(keys['KeyW']||keys['ArrowUp'])    acc.addScaledVector(fwd, speed);
    if(keys['KeyS']||keys['ArrowDown'])  acc.addScaledVector(fwd,-speed);
    if(keys['KeyA']||keys['ArrowLeft'])  acc.addScaledVector(rgt,-speed);
    if(keys['KeyD']||keys['ArrowRight']) acc.addScaledVector(rgt, speed);
    vel.add(acc);
    vel.x*=0.78;vel.z*=0.78;vel.y=0;
    isMoving=vel.lengthSq()>.0001;
    camera.position.add(vel);
    camera.position.x=Math.max(-13.4,Math.min(13.4,camera.position.x));
    camera.position.z=Math.max(-10.4,Math.min(10.4,camera.position.z));
    // Head bob
    if(isMoving){bobT+=dt*(sprint?9:6);}
    walkBob=isMoving?Math.sin(bobT)*.04*Math.min(vel.length()*8,1):walkBob*.88;
    camera.position.y=1.72+walkBob;

    // Nearby agent interactions
    var near1=nearbyAgents(3.5);
    var vtip=document.getElementById('vtip');
    if(!micOn){
      if(near1.length){
        vtip.textContent='💬 '+AGENTS[near1[0]].name+' — V eller skriv noe';
        vtip.style.display='block';
        showAgentPop(near1[0]);
      } else {
        vtip.style.display='none';
        hideAgentPop();
      }
    }

    // Area detection
    var cx=camera.position.x,cz=camera.position.z;
    var area=cx<-7.5&&cz<-4.5?'Michael sitt kontor':
             (cx>-7.5&&cx<2&&cz<-5)?'Konferanserom':
             (cx>6&&cz<-2)?'Annekset':
             (cx>6&&cz>-2)?'Pauserommet':
             cz>6?'Resepsjon':'Kontorlandskapet';
    if(area!==lastArea){lastArea=area;document.getElementById('ll').textContent='📍 '+area;}
    drawMinimap();
  }

  updateBubs();
  renderer.render(scene,camera);
}

// ── Minimap ────────────────────────────────────────────────────────
var mmCanvas=document.getElementById('mm');
var mmCtx=mmCanvas?mmCanvas.getContext('2d'):null;
function drawMinimap(){
  if(!mmCtx)return;
  var W=mmCanvas.width,H=mmCanvas.height;
  mmCtx.fillStyle='rgba(10,6,3,.85)';mmCtx.fillRect(0,0,W,H);
  mmCtx.strokeStyle='#3a2010';mmCtx.lineWidth=1;mmCtx.strokeRect(0,0,W,H);
  // Scale: room is 28x22, map is 120x94
  function wx(x){return (x+14)/28*W;}
  function wz(z){return (z+11)/22*H;}
  // Rooms
  mmCtx.strokeStyle='#3a2010';mmCtx.lineWidth=.5;
  mmCtx.strokeRect(wx(-14),wz(-11),wx(0)-wx(-14),wz(-4.5)-wz(-11)); // Michael
  mmCtx.strokeRect(wx(-7.5),wz(-11),wx(2)-wx(-7.5),wz(-5)-wz(-11)); // Conf
  mmCtx.strokeRect(wx(6),wz(-11),wx(14)-wx(6),wz(7)-wz(-11)); // Annex+Break
  // Agents
  Object.keys(agMs).forEach(function(ak){
    var a=agMs[ak];
    var ag=AGENTS[ak];
    mmCtx.fillStyle=ag&&ag.color||'#888';
    mmCtx.beginPath();mmCtx.arc(wx(a.x),wz(a.z),2.5,0,Math.PI*2);mmCtx.fill();
  });
  // Player
  mmCtx.fillStyle='#e8632a';
  mmCtx.beginPath();mmCtx.arc(wx(camera.position.x),wz(camera.position.z),3.5,0,Math.PI*2);mmCtx.fill();
  // Direction arrow
  var ax=wx(camera.position.x),az=wz(camera.position.z);
  var dx=-Math.sin(euler.y)*7,dz=-Math.cos(euler.y)*7;
  mmCtx.strokeStyle='#e8632a';mmCtx.lineWidth=1.5;
  mmCtx.beginPath();mmCtx.moveTo(ax,az);mmCtx.lineTo(ax+dx,az+dz);mmCtx.stroke();
}

// ── Agent popup when nearby ────────────────────────────────────────
var lastPopAk='';
function showAgentPop(ak){
  if(ak===lastPopAk)return;lastPopAk=ak;
  var ag=AGENTS[ak];if(!ag)return;
  var pop=document.getElementById('agpop');
  pop.style.borderColor=ag.color;
  document.getElementById('agpop-name').textContent=ag.name;
  document.getElementById('agpop-char').textContent=ag.char+' · '+ag.role;
  pop.style.display='block';
}
function hideAgentPop(){
  if(!lastPopAk)return;lastPopAk='';
  document.getElementById('agpop').style.display='none';
}

animate();
</script>
</body></html>"""

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8091, log_level="info")
