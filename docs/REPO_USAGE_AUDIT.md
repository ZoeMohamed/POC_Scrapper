# Repo usage audit

Audit ini memisahkan kode production, kode compatibility/manual, dan artefak yang tidak punya pembaca. Jalur production yang diverifikasi adalah entrypoint `index.py` → `app.main` → dashboard source-first dengan YouTube, Google Maps, TikTok, Instagram, Facebook, dan Shopee.

## Jawaban singkat: `app/collectors/playstore.py`

`playstore.py` bukan source production saat ini.

Jalur pemakaiannya adalah:

```text
SOURCES=playstore
  └─ app.config.Settings.active_sources
      └─ app.main.LEGACY_SOURCES
          └─ app.collectors.runner.build_collectors()
              └─ import .playstore (lazy)
                  └─ PlayStoreCollector
                      └─ google_play_scraper.reviews()
```

Syarat agar jalur itu hidup:

1. `SOURCES` harus memuat `playstore`.
2. `config/products.json` atau katalog yang dipakai harus mempunyai `playstore_app_ids` berisi application ID.
3. `google-play-scraper` harus terpasang.

Default production tidak memenuhi syarat pertama: `index.py` menetapkan enam source POC dan tidak memasukkan `playstore`. Semua tiga topic di `config/products.json` juga memiliki `playstore_app_ids: []`. Karena import collector sudah dibuat lazy, `google_play_scraper` tidak ikut dimuat pada cold start production.

Pemakai non-production yang masih ada:

- `scripts/scrape_once.py` menyediakan pilihan manual `playstore`.
- `app/models.py` menyimpan field `playstore_app_ids` untuk kontrak compatibility.
- `app/collectors/runner.py` mempertahankan branch legacy agar konfigurasi lama tidak rusak.

Kesimpulan: jangan hapus hanya `playstore.py` jika compatibility API/CLI harus dipertahankan. Jika Play Store resmi dipensiunkan, hapus bersama-sama branch runner, field model, pilihan `scrape_once`, dependency `google-play-scraper`, dan data/config legacy; menghapus satu file saja akan meninggalkan broken references.

## Klasifikasi file

### Production aktif

- `index.py`, `vercel.json`, `requirements.txt`: entrypoint dan deployment.
- `app/main.py`, `app/config.py`, `app/models.py`, `app/db.py`, `app/db_postgres.py`, `app/events.py`: composition, config, model, SQLite/Postgres, SSE.
- `app/api/routes_health.py`, `routes_usage.py`, `routes_topics.py`, `routes_trend.py`, `routes_maps.py`, `routes_social.py`, `routes_marketplace.py`, `routes_stream.py`: endpoint dashboard.
- `app/youtube/**`, `app/maps/**`, `app/social/**`, `app/marketplace/**`, `app/topics/**`: source adapter, parser, collector, budget, scheduler, dan topic service.
- `app/analyzer/**`, `app/nlp/**`: Gemini/lexicon, worker, preprocessing, keyword/aspect logic.
- `static/**`: dashboard HTML/CSS/JS.
- `config/topics.json`, `config/*.txt`: seed topic dan leksikon.
- `supabase/migrations/**`: schema production; tidak boleh dihapus atau diubah menjadi squash setelah migration dipakai.

### Compatibility atau manual-only, bukan jalur dashboard production

Kode berikut masih punya pemanggil atau kontrak yang terdokumentasi, sehingga tidak dihapus dalam cleanup konservatif:

- `app/api/routes_feed.py`, `routes_stats.py`, `routes_summary.py`, `routes_products.py`, `routes_ingest.py`, serta `app/api/windows.py`: endpoint v2/extension.
- `app/products.py`, `config/products.json`: katalog extension dan collector lama.
- `app/collectors/base.py`, `filters.py`, `inbox.py`, `replay.py`, `playstore.py`, `youtube.py`, `runner.py`: collector lama dan Review Bridge.
- `data/seed_comments.csv`, `data/inbox/**`: replay/inbox manual.
- `integrations/marketplace-extension/**`: Chrome extension yang memanggil endpoint products/ingest.
- `scripts/scrape_once.py`, `warmup.py`: operasi/debug manual.
- `scripts/backup_sqlite_to_supabase.py`, `maps_probe.py`, `social_probe.py`, `yt_trend_probe.py`, `reset_db.py`: operasi, probe, dan reset database.

Menghapus kelompok ini mengubah fitur yang masih tercantum di README/API atau extension, meskipun tidak dipakai halaman dashboard utama.

### Development/QA/docs, tidak masuk bundle production

- `tests/**`, `requirements-dev.txt`: regression test dan dependency pengembangan.
- `design/dashboard-concept.svg`, `mobile-concept.svg`, `visual-spec.md`: source design; bukan runtime.
- `docs/**`, `SPEC.md`, `.mcp.json`, `supabase/config.toml`: operator/spec/MCP/migration tooling.
- `.playwright-cli/**` dan PNG render hasil QA sebelumnya: artefak; PNG dan enam snapshot lama sudah dihapus, folder kini di-ignore.

Development/docs tetap disimpan karena mendukung maintenance dan reproducible deployment, tetapi `.vercelignore` mengeluarkannya dari upload Vercel.

### Sudah dihapus karena orphan atau generated

- `config/aspects.json`: tidak pernah dibaca setelah aspek sosial memakai data tersimpan.
- `scripts/scrapping_x.py`: implementasi non-demo selalu `NotImplementedError` dan tidak punya pemanggil.
- alias/helper tanpa pemanggil (`Worker`, `YoutubeCollector`, `PlaystoreCollector`, parser alias Gemini, limiter alias, `init_db`, `collect_and_save`, dan helper state/usage/event yang tidak dibaca).
- konfigurasi tanpa pembaca (`GOOGLE_MAPS_EMBED_KEY`, `MAPS_REGION`, `MAPS_MAX_PAGES`, `SOCIAL_COMMENTS_ENABLED`, `SUMMARY_MIN_REVIEWS`, `DEFAULT_WINDOW`, dan `Settings.sources_list`).
- `.playwright-cli` logs/YAML dan `design/rendered/*.png` yang hanya merupakan hasil QA/render.

## Build and request cleanup

- `requirements.txt` sekarang hanya runtime package; `pytest` dan `pytest-asyncio` ada di `requirements-dev.txt`.
- `uvicorn[standard]` diganti `uvicorn`; extras watcher/HTTP parser tidak diperlukan runtime ASGI Vercel.
- Semua dependency runtime/dev dipin ke versi yang diverifikasi pada environment saat audit.
- `.vercelignore` mengeluarkan test, script, design, docs, Supabase tooling, MCP, `.env`, dan artefak lokal.
- Refresh dashboard dipisah per source. Filter/sort YouTube hanya memanggil `/api/trend/videos`; `trend_tick` hanya refresh YouTube; event sentimen hanya refresh social. Snapshot yang ada tidak dikosongkan saat background refresh.
- Backup SQLite→Supabase sekarang mencakup `marketplace_products` dan `marketplace_refreshes`.

## Verification evidence

- `PYTHONPATH=. .venv/bin/python -m pytest -q`: **73 passed**.
- `node --check static/app.js`, `static/ui.js`, `static/api.js`: pass.
- `python -m compileall app scripts`: pass.
- `git diff --check`: pass.
- Production-like local smoke: dashboard loaded; all seven navigation views (Ringkasan + six source views) opened on desktop; Google Maps opened on mobile; no console/page errors; no horizontal overflow.
- Filter request audit: changing YouTube type emitted one `/api/trend/videos` request and zero `/api/trend` refresh requests.
- Cold import after lazy compatibility imports: Play Store module is not loaded on the normal production source set.
