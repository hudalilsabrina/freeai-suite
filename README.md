# Free.ai Suite

Factory akun + panen API key dari **[free.ai](https://free.ai/)** — penyedia
endpoint **OpenAI-compatible** dengan free tier **30.000 token/hari** per akun
terverifikasi.

Suite ini: buat akun → verifikasi email (kode 6-digit) → generate API key →
test chat → inject ke 9router.

## Kenapa suite terpisah?

free.ai **bukan** gateway jaringan Gonka — ia penyedia independen
(Muddy Holdings LLC, Australia) dengan 511 model self-hosted. Dipisah dari
`gonka-suite` agar tidak tercampur.

## Detail layanan

| Item | Nilai |
|---|---|
| Base URL | `https://api.free.ai/v1` |
| Auth | `Authorization: Bearer sk-free-...` |
| Endpoint chat | `POST /v1/chat/completions` (OpenAI-compatible) |
| Endpoint model | `GET /v1/models` → `{"models":[...]}` (511 model) |
| Free tier | 30.000 token/hari (2.500/hari bila email belum diverifikasi) |
| Batas developer | 1.000 request/bulan, rate-limit 60/menit |
| Key prefix | `sk-free-` |
| Model default | `qwen7b` (self-hosted, gratis dari pool harian) |
| Rate-limit signup | ~5 akun/jam per IP |

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install playwright rich
.venv/bin/playwright install chromium
```

## Konfigurasi

Salin `config.example.toml` → `config.toml` dan isi endpoint temp-mail Anda
(atau set env `TEMPIK_BASE`). Untuk sync ke 9router, isi `[router] url` &
`password` (atau env `NINEROUTER_URL` / `NINEROUTER_PASS`).

## Command

```bash
./run.sh harvest      # buat 1 akun (signup -> verify -> API key)
./run.sh batch <n>    # buat N akun berurutan
./run.sh test         # test semua API key (chat nyata)
./run.sh report       # ringkasan akun
./run.sh sync         # inject akun ke 9router (node openai-compatible)
```

Batch runner dengan penanganan rate-limit:

```bash
.venv/bin/python batch.py <n>                 # berhenti rapi saat kena limit
.venv/bin/python batch.py <n> --cooldown-wait # tunggu 1 jam lalu lanjut
```

## Alur harvest (reverse-engineered)

1. **Inbox** temp-mail (`data/inboxes.json`).
2. **Signup**: `POST https://free.ai/signup/` (email + password + hidden
   `signup_token` anti-bot).
3. **Verifikasi**: halaman `/verify/`, kode 6-digit dari email.
   Field `#verify-code` menolak input keyboard biasa → nilainya di-set via
   native value setter lalu form di-submit dengan `requestSubmit()`.
4. **API key**: `POST https://free.ai/api/v1/api-keys/` (butuh cookie
   `csrftoken`). Key penuh **hanya** dikembalikan saat create; `GET` hanya
   mengembalikan prefix.
5. **Test chat** → simpan ke `accounts.txt`.

## Format akun (`accounts.txt`)

```
email:password:api_key:base_url
```

`base_url` mengandung `:` (mis. `https://...`) → parsing **wajib**
`split(":", 3)` dari kiri. **Jangan** pakai `rsplit` — akan memotong base_url
dan merusak key (bug yang pernah terjadi).

## Temp-mail

Memakai **[tempik](https://github.com/hirotomasato/tempik)** — layanan
disposable email self-hosted. Klien di `src/tempmail.py`; endpoint tempik
(`/api/session`, `/api/inboxes`, `/api/inboxes/{addr}/messages`).

## Integrasi 9router

`./run.sh sync` membuat node `openai-compatible` bernama `freeai-free-ai`
dengan prefix `freeai` dan meng-inject semua akun sebagai koneksi.

## Catatan keamanan

- Jangan commit `accounts.txt` / `data/` (berisi kredensial) — sudah masuk
  `.gitignore`.
- `config.toml` juga di-gitignore; hanya `config.example.toml` yang publik.

## Credits

- **[tempik](https://github.com/hirotomasato/tempik)** — self-hosted disposable
  temp-mail service (sumber API klien email).
- **free.ai** — penyedia inference OpenAI-compatible dengan free tier harian.
