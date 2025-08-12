from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from nc_vip_dmv.config import load_config
from nc_vip_dmv.core.scheduler import Scheduler
from nc_vip_dmv.core.subscriptions import SubscriptionsStore
from nc_vip_dmv.core.discovery import discover_offices_playwright

# Load .env early so env vars are available during import evaluation
load_dotenv()

app = FastAPI(title="NC VIP-DMV")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_PATH = Path(os.getenv("NCVIP_CONFIG", "config.yaml"))
CHECKER = os.getenv("NCVIP_CHECKER", None)
NO_NOTIFY = os.getenv("NCVIP_NO_NOTIFY", "true").lower() in {"1", "true", "yes"}

scheduler: Optional[Scheduler] = None
subscriptions: Optional[SubscriptionsStore] = None
admin_token_env_name: Optional[str] = None

# Cached discovered offices
offices_cache: List[Dict[str, str]] = []


@app.on_event("startup")
async def startup_event():
    global scheduler, subscriptions, admin_token_env_name, offices_cache
    config = load_config(CONFIG_PATH)

    # Optional env overrides for notifier enabled flags
    sms_enabled_env = os.getenv("NCVIP_SMS_ENABLED")
    if sms_enabled_env is not None:
        config.notifiers.sms.enabled = sms_enabled_env.lower() in {"1", "true", "yes"}
    email_enabled_env = os.getenv("NCVIP_EMAIL_ENABLED")
    if email_enabled_env is not None:
        config.notifiers.email.enabled = email_enabled_env.lower() in {"1", "true", "yes"}
    discord_enabled_env = os.getenv("NCVIP_DISCORD_ENABLED")
    if discord_enabled_env is not None:
        config.notifiers.discord.enabled = discord_enabled_env.lower() in {"1", "true", "yes"}

    scheduler = Scheduler(config, notifications_enabled=not NO_NOTIFY)
    subscriptions = SubscriptionsStore(path=config.settings.subscriptions_file)
    scheduler.attach_subscriptions(subscriptions)
    admin_token_env_name = config.admin_token_env

    # Kick off background discovery to populate offices cache
    async def _load_offices_bg():
        try:
            discovered = await discover_offices_playwright()
            offices_cache = discovered  # type: ignore[assignment]
        except Exception:
            # Best-effort; keep running without discovery
            offices_cache = []  # type: ignore[assignment]

    asyncio.create_task(_load_offices_bg())

    # run scheduler in background
    asyncio.create_task(scheduler.run(checker_override=CHECKER, run_once=False))


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/results")
async def api_results():
    if scheduler is None:
        return JSONResponse({"error": "scheduler_not_ready"}, status_code=503)
    return {"results": scheduler.latest_results}


@app.get("/api/offices")
async def api_offices(source: Optional[str] = Query(default="all", description="configured|discovered|all")):
    if scheduler is None:
        return JSONResponse({"error": "scheduler_not_ready"}, status_code=503)
    configured = [{"name": o.name, "url": o.url} for o in scheduler.config.offices]
    discovered = offices_cache or []
    if source == "configured":
        return {"offices": configured}
    if source == "discovered":
        return {"offices": discovered}
    # Merge unique by name (prefer configured URL when duplicate)
    by_name: Dict[str, Dict[str, str]] = {o["name"]: o for o in discovered}
    for o in configured:
        by_name[o["name"]] = o
    merged = [by_name[k] for k in sorted(by_name.keys())]
    return {"offices": merged}


@app.get("/api/subscriptions")
async def list_subscriptions(authorization: Optional[str] = Header(default=None)):
    # admin-only
    expected_token = os.getenv(admin_token_env_name or "NCVIP_ADMIN_TOKEN", "").strip()
    if not expected_token or authorization != f"Bearer {expected_token}":
        raise HTTPException(status_code=403, detail="forbidden")
    return {"subscriptions": subscriptions._data if subscriptions else {}}


@app.post("/api/subscriptions")
async def upsert_subscription(payload: dict):
    # payload: { email: str, offices: [str] }
    if not subscriptions:
        raise HTTPException(status_code=503, detail="subs_not_ready")
    email = (payload.get("email") or "").strip().lower()
    offices = payload.get("offices") or []
    if not email or not isinstance(offices, list):
        raise HTTPException(status_code=400, detail="invalid_payload")
    # validate offices
    known = {o["name"] for o in (offices_cache or [])} | ({o.name for o in scheduler.config.offices} if scheduler else set())
    for off in offices:
        if off not in known:
            raise HTTPException(status_code=400, detail=f"unknown_office: {off}")
    subscriptions.set_subscription(email, offices)
    return {"ok": True}


@app.delete("/api/subscriptions")
async def delete_subscription(payload: dict):
    if not subscriptions:
        raise HTTPException(status_code=503, detail="subs_not_ready")
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="invalid_payload")
    subscriptions.remove(email)
    return {"ok": True}


@app.post("/api/test-sms")
async def api_test_sms(authorization: Optional[str] = Header(default=None)):
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler_not_ready")
    if not scheduler.config.notifiers.sms.enabled:
        raise HTTPException(status_code=400, detail="sms_not_enabled")

    expected_token = os.getenv(admin_token_env_name or "NCVIP_ADMIN_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=500, detail="admin_token_not_set")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    provided = authorization.split(" ", 1)[1].strip()
    if provided != expected_token:
        raise HTTPException(status_code=403, detail="invalid_token")

    await scheduler._notify_sms(office_name="TEST", office_url=None, signature="Test message from NC VIP-DMV")
    return {"ok": True}


@app.post("/api/test-email")
async def api_test_email(authorization: Optional[str] = Header(default=None)):
    if scheduler is None:
        raise HTTPException(status_code=503, detail="scheduler_not_ready")
    if not scheduler.config.notifiers.email.enabled:
        raise HTTPException(status_code=400, detail="email_not_enabled")

    expected_token = os.getenv(admin_token_env_name or "NCVIP_ADMIN_TOKEN", "").strip()
    if not expected_token:
        raise HTTPException(status_code=500, detail="admin_token_not_set")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    provided = authorization.split(" ", 1)[1].strip()
    if provided != expected_token:
        raise HTTPException(status_code=403, detail="invalid_token")

    # Use configured test email as recipient for this admin-triggered test
    to_email = os.getenv(scheduler.config.notifiers.email.test_to_email_env, "").strip()
    if not to_email:
        raise HTTPException(status_code=400, detail="missing_test_to_email_env")
    await scheduler._notify_email_to(to_email, office_name="TEST", office_url=None, signature="Test email from NC VIP-DMV")
    return {"ok": True}


@app.post("/api/admin/discover-offices")
async def admin_discover_offices(authorization: Optional[str] = Header(default=None)):
    expected_token = os.getenv(admin_token_env_name or "NCVIP_ADMIN_TOKEN", "").strip()
    if not expected_token or authorization != f"Bearer {expected_token}":
        raise HTTPException(status_code=403, detail="forbidden")
    offices = await discover_offices_playwright()
    return {"offices": offices, "count": len(offices)}


DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>NC VIP-DMV</title>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; }
    header { display: flex; align-items: center; gap: 12px; }
    h1 { margin: 0; font-size: 22px; }
    .meta { color: #666; font-size: 13px; }
    .card { border: 1px solid #eee; border-radius: 10px; padding: 16px; margin: 12px 0; }
    .ok { color: #0a8; }
    .no { color: #999; }
    .yes { color: #d22; font-weight: 600; }
    code { background: #f6f8fa; padding: 2px 4px; border-radius: 6px; }
  </style>
</head>
<body>
  <header>
    <h1>NC VIP-DMV</h1>
    <div class="meta">Live availability monitor</div>
  </header>

  <div id="list"></div>

  <script>
    async function fetchResults() {
      try {
        const res = await fetch('/api/results');
        const json = await res.json();
        const items = json.results || [];
        const container = document.getElementById('list');
        container.innerHTML = '';
        items.forEach(it => {
          const div = document.createElement('div');
          div.className = 'card';
          const status = it.available ? '<span class="yes">AVAILABLE</span>' : '<span class="no">none</span>';
          const samples = (it.samples || []).map(s => `<li><code>${s}</code></li>`).join('');
          div.innerHTML = `
            <div><strong>${it.office}</strong> — ${status}</div>
            <div style=\"font-size:13px; color:#666;\">${it.url ? `<a href=\"${it.url}\" target=\"_blank\">${it.url}</a>` : ''}</div>
            <div>count: ${it.count}</div>
            <ul>${samples}</ul>
          `;
          container.appendChild(div);
        });
      } catch (e) {
        console.error(e);
      }
    }

    fetchResults();
    setInterval(fetchResults, 4000);
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(DASHBOARD_HTML)
