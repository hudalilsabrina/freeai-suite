#!/usr/bin/env python3
"""Free.ai Suite - CLI: harvest akun, test key, sync ke 9router.

Command:
  harvest              Buat 1 akun (signup -> verify -> API key)
  batch <n>            Buat N akun berurutan
  test                 Test semua API key tersimpan (chat nyata)
  report               Ringkasan akun
  sync                 Inject akun ke 9router (node openai-compatible)
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rich.console import Console
from rich.table import Table
from rich import box

from src import freeai
from src.freeai import FA_BASE, KEY_PREFIX

C = Console()
ACCOUNTS = Path(__file__).resolve().parent / "accounts.txt"


async def cmd_harvest():
    r = await freeai.harvest_freeai()
    red = {k: (v if not isinstance(v, str) or len(v) < 24 else v[:10] + "..." + v[-4:])
           for k, v in r.items()}
    C.print(json.dumps(red, indent=1, default=str))
    C.print("[green]KEY diperoleh[/]" if r.get("ok") else f"[yellow]GAGAL: {r.get('error')}[/]")


async def cmd_batch(n):
    ok = 0
    for i in range(1, n + 1):
        C.print(f"[cyan]=== Akun {i}/{n} ===[/]")
        r = await freeai.harvest_freeai()
        if r.get("ok"):
            ok += 1
            C.print(f"[green]  OK {r.get('email')}[/]")
        else:
            C.print(f"[yellow]  gagal: {r.get('error')}[/]")
    C.print(f"\n[bold]Batch: {ok}/{n} sukses[/]")


def cmd_test():
    accs = freeai.parse_accounts()
    if not accs:
        C.print("[yellow]Belum ada akun. Jalankan: ./run.sh harvest[/]")
        return
    t = Table(box=box.ROUNDED, title=f"free.ai keys ({len(accs)})")
    t.add_column("Email", style="cyan")
    t.add_column("OK", style="green")
    t.add_column("Model", style="white")
    t.add_column("Error", style="red", overflow="fold")
    ok = 0
    for a in accs:
        r = freeai.test_chat(a["base_url"], a["key"])
        ok += bool(r.get("ok"))
        t.add_row(a["email"][:28], "yes" if r.get("ok") else "no",
                  r.get("model") or "-", (r.get("error") or "")[:40])
    C.print(t)
    C.print(f"[bold]{ok}/{len(accs)} valid[/]")


def cmd_report():
    accs = freeai.parse_accounts()
    C.print(f"[bold]Total akun free.ai: {len(accs)}[/]")
    for a in accs:
        C.print(f"  {a['email']:<34} key {a['key'][:12]}...  {a['base_url']}")


def cmd_sync():
    from src import router9
    accs = freeai.parse_accounts()
    if not accs:
        C.print("[yellow]Tidak ada akun untuk disync[/]")
        return
    r = router9.ingest_gateway("freeai-free-ai", "freeai", FA_BASE, accs, None)
    C.print(json.dumps(r))


def main():
    ap = argparse.ArgumentParser(prog="freeai", description="Free.ai Suite")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("harvest")
    b = sub.add_parser("batch")
    b.add_argument("n", type=int)
    sub.add_parser("test")
    sub.add_parser("report")
    sub.add_parser("sync")
    a = ap.parse_args()
    if a.cmd == "harvest":
        asyncio.run(cmd_harvest())
    elif a.cmd == "batch":
        asyncio.run(cmd_batch(a.n))
    elif a.cmd == "test":
        cmd_test()
    elif a.cmd == "report":
        cmd_report()
    elif a.cmd == "sync":
        cmd_sync()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
