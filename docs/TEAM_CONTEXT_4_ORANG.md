# POC Scrapper — Team Context 4 Orang

Dokumen ini adalah satu-satunya context operasional yang perlu diberikan ke AI dan teammate bersama README.md serta SRS.md. Cakupan production: YouTube, Google Maps, TikTok, Instagram, Facebook, dan Shopee melalui adapter/API yang sah. Jangan mengklaim data live tanpa SourceRun sukses, timestamp, dan evidence.

## Aturan kerja

- Gunakan clone/worktree terpisah dan branch team/1-sources, team/2-platform, team/3-intelligence, atau team/4-frontend.
- Jangan commit ke main.
- API key hanya di environment/secret manager; jangan tulis di kode, log, fixture, screenshot, atau prompt.
- Test provider dan Gemini harus offline dengan fixture/fake client.
- Jangan hapus module lama sebelum replacement lulus test dan route compatibility terverifikasi.
- Pipeline wajib: provider adapter -> Evidence -> SourceRun -> Analysis -> API/SSE -> UI.
- Status yang sah: disabled, misconfigured, queued, running, fresh, empty, stale, budget_exhausted, error.
- Fixture/demo tidak boleh diberi label live.

## Onboarding dan branching

Setiap anggota memakai clone atau worktree sendiri. Branch resmi dibuat dari baseline yang sama:

~~~text
team/1-sources
team/2-platform
team/3-intelligence
team/4-frontend
~~~

Setup pertama:

~~~bash
git clone git@github.com:ZoeMohamed/POC_Scrapper.git
cd POC_Scrapper
git fetch origin
git switch <branch-role>
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
~~

Sinkronisasi sebelum mulai setiap sesi:

~~~bash
git fetch origin
git rebase origin/main
.venv/bin/python -m pytest -q
~~

Push pekerjaan:

~~~bash
git status --short
git diff --check
git add <file-milik-role>
git commit -m "feat(area): ringkasan perubahan"
git push origin HEAD
~~

Aturan PR:
- target selalu main;
- jangan force-push main;
- satu PR hanya satu workstream;
- perubahan contract harus direview semua role;
- konflik file ownership diselesaikan oleh owner file;
- PR wajib mencantumkan test, status provider, risiko kuota, dan rollback;
- sesudah merge, semua branch rebase dari origin/main.

## Konteks AI bersama

Kamu bekerja di repo POC Scrapper Python/FastAPI. Frontend adalah vanilla HTML/CSS/JS di static/. SQLite dipakai development/test; Supabase Postgres production. Provider dapat timeout, kosong, rate-limit, permission error, atau kehabisan budget.

Evidence minimum:
~~~json
{
  "source": "youtube|maps|tiktok|instagram|facebook|shopee",
  "topic_id": "id",
  "external_id": "provider-id",
  "provider_run_id": "run-id-or-null",
  "title": "judul atau nama tempat",
  "text": "caption atau ulasan",
  "url": "https://...",
  "published_at": "ISO-8601-or-null",
  "collected_at": "ISO-8601",
  "relevance": 0.0,
  "raw_count": 0,
  "relevant_count": 0
}
~~~

Analysis minimum:
~~~json
{
  "label": "positif|negatif|netral|pending",
  "score": 0.0,
  "confidence": 0.0,
  "aspects": [],
  "analyzer": "gemini|lexicon|mock|pending",
  "analyzed_at": "ISO-8601-or-null"
}
~~~

SSE/status event minimum:
~~~json
{
  "event": "source_status|progress|evidence_new|analysis_updated|error",
  "topic_id": "id",
  "source": "instagram",
  "status": "running",
  "progress": 0.0,
  "message": "Mengambil post publik",
  "updated_at": "ISO-8601"
}
~~~

## Pembagian role dan file

### Orang 1 — Data Source & Apify

Branch: team/1-sources

File:
~~~text
app/youtube/**
app/maps/**
app/social/** kecuali app/social/sentiment.py
app/marketplace/**
app/collectors/**
scripts/*probe*
tests/test_youtube*
tests/test_apify_*
tests/test_social_*
tests/test_marketplace_*
tests/fixtures/sources/**
~~~

Tugas:
- normalisasi YouTube, Maps, TikTok, Instagram, Facebook, dan Shopee menjadi Evidence;
- filter relevansi produk dan deduplikasi;
- bounded pagination/cache untuk menghemat run;
- fixture success, empty, invalid payload, timeout/rate-limit;
- provider_run_id, raw_count, relevant_count, error_code.

Tidak boleh mengubah backend, analyzer, atau static/. Play Store, replay, dan inbox bukan source production aktif.

### Orang 2 — Backend, Supabase & Integration

Branch: team/2-platform

File:
~~~text
app/main.py
app/config.py
app/models.py
app/db.py
app/db_postgres.py
app/events.py
app/products.py
app/topics/**
app/api/**
migrations/** atau sql/**
index.py
vercel.json
docs/CONTRACTS.md
tests/test_api*.py
tests/test_postgres_backend.py
tests/test_usage_v3.py
tests/test_source_usage.py
~~~

Tugas:
- contract Evidence, SourceRun, Analysis, SSE;
- source_runs ledger idempotent per topic + source + window;
- snapshot API, refresh background, progress, usage, budget;
- SQLite dan Supabase memakai interface repository yang sama;
- route health, topics, feed, maps, social, marketplace, trend, usage, stream;
- timeout, retry terbatas, lock, dan error code aman.

Tidak boleh mengubah detail adapter, analyzer/NLP, atau static/.

### Orang 3 — Intelligence, Gemini & Data Quality

Branch: team/3-intelligence

File:
~~~text
app/analyzer/**
app/nlp/**
app/social/sentiment.py
app/youtube/content_type.py
tests/test_gemini*.py
tests/test_lexicon.py
tests/test_preprocess.py
tests/test_content_type_v3.py
tests/test_worker.py
tests/fixtures/analysis/**
~~~

Tugas:
- preprocess bahasa Indonesia, negasi, slang, emoji, mixed language;
- label positif/negatif/netral/pending;
- Gemini pool/timeout/limiter dan fallback lexicon/mock;
- relevance filter sebelum sentiment;
- score, confidence, aspects, analyzer, analyzed_at;
- golden set minimal 50 contoh dan regression test.

Contoh wajib:
- "Siapa sih yang nggak suka es satu ini" -> positif.
- "Rasanya enak, tapi terlalu mahal" -> rasa positif, harga negatif.
- "Launching produk hari ini" -> netral.
- teks tanpa produk target -> ditolak.
- emoji saja -> pending/netral confidence rendah.

### Orang 4 — Frontend, UX, QA & Release

Branch: team/4-frontend

File:
~~~text
static/**
tests/e2e/**
tests/smoke/**
playwright.config.*
docs/UX_*.md
README.md
~~~

Tugas:
- sidebar Ringkasan, YouTube, Google Maps, TikTok, Instagram, Facebook, Shopee, Usage;
- source status, last sync, progress, evidence count, sentiment, error, empty, refresh;
- snapshot lama tetap terlihat saat refresh;
- mock JSON/SSE sebelum backend selesai;
- E2E loading, success, empty, error, stale, filter, mobile, keyboard;
- production smoke dan release note.

## Sprint live coding 4 jam

### 00:00–00:15 — baseline

~~~bash
git fetch origin
git switch main
git pull --ff-only
source .venv/bin/activate
.venv/bin/python -m pytest -q
~~~

Pilih satu topic demo dan satu provider live paling stabil. Jangan menunggu semua credential.

### 00:15–00:35 — mini contract

Orang 2 menyiapkan fake topic, fake SourceRun, fake Evidence, snapshot API, dan status event. Semua role review shape yang sama.

### 00:35–01:45 — parallel build

- Orang 1: satu probe/provider + normalizer + fixture.
- Orang 2: refresh/snapshot/status endpoint.
- Orang 3: sentiment/fallback/golden examples.
- Orang 4: dashboard dengan mock contract.

### 01:45–02:15 — first vertical slice

Wiring:
~~~text
provider/fixture -> SourceRun -> Evidence -> analyzer -> snapshot API -> UI
~~~

Satu topic harus dapat refresh tanpa menunggu semua source.

### 02:15–03:00 — source cards dan failure states

Tampilkan keenam source; bedakan real, fixture, empty, misconfigured, stale, dan error. Jangan menghapus snapshot lama.

### 03:00–03:30 — QA

~~~bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q app scripts
git diff --check
node --check static/app.js
node --check static/api.js
node --check static/state.js
node --check static/ui.js
~~~

### 03:30–04:00 — freeze dan demo

~~~bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/topics
curl -fsS http://127.0.0.1:8000/api/usage
~~~

Jangan memulai refactor besar pada 30 menit terakhir. Catat source mana real dan mana fixture.

## AI coding protocol

Sebelum coding, AI wajib:
1. inspeksi file dan call graph;
2. menyebut file yang akan diubah;
3. menyebut contract yang dipakai;
4. membuat perubahan terkecil;
5. menjalankan test terkait;
6. menampilkan diff summary dan risiko.

Format laporan:
~~~text
STATUS: DONE | PARTIAL | BLOCKED
SCOPE: unit kecil yang dikerjakan
FILES: daftar file
CONTRACT: tidak berubah | berubah + alasan
TESTS: command + hasil
SECURITY: tidak ada secret
RISKS: provider/kuota/migration/UX
NEXT: satu langkah
~~~

## Cleanup policy

Production source aktif hanya enam source di SRS. Module berikut tetap compatibility/manual-only karena masih direferensikan oleh test atau CLI:
- app/collectors/replay.py dan tests/fixtures/replay_comments.csv;
- app/collectors/inbox.py dan data/inbox/.gitkeep;
- app/collectors/playstore.py;
- scripts/scrape_once.py dan scripts/warmup.py.

Jangan menghapus replay fixture satu file saja. Jika replay benar-benar dipensiunkan, hapus atau migrasikan seluruh chain: collector, runner branch, config.seed_comments_path, script, test fixture, model source, dan dokumentasinya dalam satu PR terpisah.

## Definition of done

- satu topic dapat refresh end-to-end;
- minimal satu source terbukti real atau status error provider terbukti;
- source lain tidak dipalsukan sebagai live;
- sentiment Indonesia tampil;
- loading/progress/error/empty/stale tidak blank;
- duplicate refresh tidak menggandakan data;
- test offline dan smoke lulus;
- API key tidak masuk Git, log, response, screenshot;
- production hanya disebut live jika SourceRun sukses dan timestamp tersedia.
