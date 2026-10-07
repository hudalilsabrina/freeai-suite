"""free.ai API client + account harvester.

free.ai (Muddy Holdings LLC) menyediakan endpoint OpenAI-compatible di
https://api.free.ai/v1 dengan free tier 30.000 token/hari untuk akun yang
sudah diverifikasi email.

Alur signup (Django):
  1. POST /signup/  (email + password + hidden signup_token)
  2. Halaman /verify/ -> kode 6-digit dikirim ke email
  3. POST /verify/ dengan kode -> akun terkonfirmasi, pool naik ke 30K/hari
  4. POST /api/v1/api-keys/ -> generate key (format sk-free-...)

Catatan teknis:
- Field kode verifikasi (#verify-code) menolak input keyboard biasa; nilainya
  harus di-set via native value setter lalu form di-submit dengan requestSubmit().
- API key penuh hanya dikembalikan saat create; GET /api/v1/api-keys/ hanya
  mengembalikan prefix.
- Endpoint /models mengembalikan {"models":[...]} (bukan {"data":[...]}).
"""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

from .config import DATA_DIR
from .inboxstore import save as save_inbox, get as get_inbox
from .tempmail import TempikClient

C = Console()

FA_HOST = "https://free.ai"
FA_BASE = "https://api.free.ai/v1"
FA_KEY_API = f"{FA_HOST}/api/v1/api-keys/"
KEY_PREFIX = "sk-free-"
ACCOUNTS = Path(DATA_DIR).parent / "accounts.txt"

DEFAULT_MODEL = "qwen7b"   # self-hosted, gratis dari pool harian


def _rand_password(n: int = 12) -> str:
    """Password acak per akun (jangan pernah hardcode password nyata)."""
    import random
    import string
    core = "".join(random.choices(string.ascii_letters + string.digits, k=n))
    return f"Fa{core}!7"

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


# --------------------------- API helpers ---------------------------

def _headers(key: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {key}", "User-Agent": _UA,
            "Accept": "application/json"}


def list_models(key: str, timeout: int = 30) -> list:
    """Ambil daftar model (dukung bentuk OpenAI maupun {'models':[...]})."""
    req = urllib.request.Request(f"{FA_BASE}/models", headers=_headers(key))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    raw = d.get("data") or d.get("models") or []
    return [m.get("id") for m in raw]


def test_chat(base_url: str, key: str, model: str = DEFAULT_MODEL,
              timeout: int = 90) -> Dict[str, Any]:
    """Test chat nyata. Mengembalikan {'ok': bool, ...}."""
    out: Dict[str, Any] = {"base_url": base_url, "ok": False}
    try:
        body = json.dumps({"model": model,
                           "messages": [{"role": "user", "content": "Reply exactly: PONG"}],
                           "max_tokens": 16}).encode()
        req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions",
                                     data=body, headers={**_headers(key),
                                                         "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        out["ok"] = True
        out["model"] = model
        out["usage"] = d.get("usage")
        out["reply"] = (d.get("choices", [{}])[0].get("message", {}).get("content", "") or "")[:60]
    except urllib.error.HTTPError as e:
        out["error"] = f"HTTP {e.code}: {e.read().decode()[:120]}"
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


# --------------------------- Harvester ---------------------------

def _read_code(session_id: str, email: str, timeout: int = 150) -> Optional[str]:
    """Poll inbox untuk kode verifikasi 6-digit (ambil yang terbaru)."""
    c = TempikClient()
    c.session_id = session_id
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            msgs = c.get_messages(email) or []
            for m in msgs:
                plain = re.sub(r"<[^>]+>", " ",
                               (m.get("body", "") or "") + " " + (m.get("subject", "") or ""))
                codes = re.findall(r"\b(\d{6})\b", plain)
                if codes:
                    return codes[-1]
        except Exception:
            pass
        time.sleep(5)
    return None


async def harvest_freeai(headless: bool = True, password: str = None,
                         timeout_verify: int = 150) -> Dict[str, Any]:
    """Buat 1 akun free.ai: signup -> verifikasi kode -> generate API key."""
    import asyncio
    from playwright.async_api import async_playwright
    from .stealth import launch_stealth_browser, create_stealth_context

    password = password or _rand_password()
    out: Dict[str, Any] = {"site": "freeai", "ok": False, "base_url": FA_BASE}
    tc = TempikClient()
    email = tc.create_inbox()
    save_inbox("freeai", email, tc.session_id, password)
    out["email"] = email
    C.print(f"[cyan]free.ai[/] inbox: {email}")

    async with async_playwright() as p:
        browser = await launch_stealth_browser(p, headless=headless)
        ctx = await create_stealth_context(browser)
        page = await ctx.new_page()
        try:
            await page.goto(f"{FA_HOST}/signup/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            await page.fill("#register-email", email)
            await page.wait_for_timeout(400)
            await page.fill("#register-password", password)
            await page.wait_for_timeout(400)
            await page.evaluate("""() => {
                const b = [...document.querySelectorAll('button')].find(x => /sign up free/i.test(x.innerText));
                if (b) b.click();
            }""")
            await page.wait_for_timeout(5000)
            out["after_signup_url"] = page.url
            body = await page.evaluate("document.body.innerText")
            m = re.search(r"(too many signups[^.\n]*)", body, re.I)
            if m:
                out["error"] = m.group(1)[:120]
                return out
            # verifikasi kode
            code = await asyncio.to_thread(_read_code, tc.session_id, email, timeout_verify)
            out["code"] = code
            if code:
                await page.evaluate("""(code) => {
                    const e = document.querySelector('#verify-code');
                    if (!e) return;
                    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    set.call(e, code);
                    e.dispatchEvent(new Event('input', {bubbles:true}));
                    const f = e.form;
                    if (f) { if (f.requestSubmit) f.requestSubmit(); else f.submit(); }
                }""", code)
                await page.wait_for_timeout(6000)
            out["final_url"] = page.url
            # generate API key
            await page.goto(f"{FA_HOST}/account/", wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            key = await page.evaluate("""(async () => {
                const csrf = (document.cookie.match(/csrftoken=([^;]+)/)||[])[1];
                const r = await fetch('/api/v1/api-keys/', {method:'POST',
                    headers:{'X-CSRFToken':csrf, 'Content-Type':'application/json'},
                    credentials:'include', body: JSON.stringify({name:'freeai-suite'})});
                const j = await r.json();
                return j.key || null;
            })""")
            if key:
                out["key"] = key
                out["ok"] = True
                _append_account(email, password, key, FA_BASE)
            else:
                out["error"] = out.get("error") or "key tidak ter-generate (verifikasi gagal)"
        except Exception as e:
            out["error"] = str(e)[:150]
        finally:
            try:
                await ctx.close(); await browser.close()
            except Exception:
                pass
    return out


def _append_account(email: str, password: str, key: str, base: str):
    ACCOUNTS.open("a").write(f"{email}:{password}:{key}:{base}\n")


# --------------------------- Account store ---------------------------

def parse_accounts(path: Path = None) -> list:
    """Parse accounts.txt: email:password:key:base_url.

    PENTING: gunakan split(':', 3) dari kiri — jangan rsplit, karena base_url
    mengandung ':' (https://...) sehingga rsplit akan memotong base_url.
    """
    path = path or ACCOUNTS
    out = []
    if not path.exists():
        return out
    for ln in path.read_text().strip().splitlines():
        ln = ln.strip()
        if not ln or ln.count(":") < 3:
            continue
        try:
            email, password, key, base = ln.split(":", 3)
            out.append({"email": email, "password": password, "key": key, "base_url": base})
        except ValueError:
            continue
    return out
