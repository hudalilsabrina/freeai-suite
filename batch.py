#!/usr/bin/env python3
"""Batch harvester free.ai: buat N akun, log tiap hasil, verifikasi chat.

Rate-limit free.ai ~5 akun/jam per IP. Runner ini mendeteksi pesan
"too many signups" dan berhenti dengan rapi (menyimpan progres) alih-alih
membuang percobaan.

Pakai: .venv/bin/python batch.py <n> [--cooldown-wait]
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import freeai

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)
RATE_HINT = "too many signups"


def _log(idx, r):
    rec = {"idx": idx, "ts": int(time.time()), "ok": bool(r.get("ok")),
           "email": r.get("email"), "error": (r.get("error") or "")[:150]}
    if r.get("key"):
        t = freeai.test_chat(r.get("base_url") or freeai.FA_BASE, r["key"])
        rec["chat_ok"] = bool(t.get("ok"))
        rec["model"] = t.get("model")
        if not t.get("ok"):
            rec["chat_error"] = str(t.get("error"))[:120]
    with (DATA / "batch_freeai.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--cooldown-wait", action="store_true",
                    help="tunggu 1 jam saat kena rate-limit lalu lanjut")
    a = ap.parse_args()
    ok = 0
    i = 0
    while i < a.n:
        i += 1
        r = await freeai.harvest_freeai()
        rec = _log(i, r)
        if rec["ok"]:
            ok += 1
        print(f"[{i}] {'OK ' if rec['ok'] else 'FAIL'} {rec.get('email')} "
              f"{rec.get('error', '')}", flush=True)
        if RATE_HINT in (r.get("error") or "").lower():
            print("[batch] rate-limit terdeteksi.", flush=True)
            if a.cooldown_wait:
                print("[batch] menunggu 1 jam...", flush=True)
                await asyncio.sleep(3600)
            else:
                print(f"[batch] berhenti. progres tersimpan. sukses {ok}/{i}", flush=True)
                break
        print(f"=== progress: {i}/{a.n}, sukses {ok} ===", flush=True)
    print(f"SELESAI free.ai: {ok}/{a.n} sukses", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
