# Pembagian Rebuild untuk 5 Orang

Dokumen ini membagi implementasi [SRS v4](../SRS.md) kepada lima orang. Pembagian dibuat berdasarkan batas modul supaya setiap orang dapat bekerja paralel tanpa mengedit file yang sama.

## 1. Aturan kerja bersama

1. Gunakan branch `team/<nomor>-<area>`, satu tujuan per pull request.
2. Pemilik file adalah reviewer wajib. Orang lain tidak mengedit file tersebut tanpa handoff tertulis.
3. `app/main.py`, `app/config.py`, `app/models.py`, dan migration hanya dimiliki Orang 3. Engineer source mengekspor class/factory; Orang 3 yang memasangnya.
4. `static/**` hanya dimiliki Orang 5. Engineer backend menyediakan mock response atau OpenAPI, bukan mengubah UI.
5. `app/analyzer/**`, `app/nlp/**`, dan keputusan label sentimen hanya dimiliki Orang 4.
6. Test provider tidak boleh menggunakan API sungguhan. Probe manual dipisahkan di `scripts/`.
7. Secret tidak boleh masuk commit, fixture, screenshot, atau log.
8. Sebelum coding, kelima orang menyetujui kontrak pada Gate 0.

## 2. Gate 0 — kontrak bersama (hari 1)

Output wajib sebelum pekerjaan paralel:

- bentuk `Evidence`, `SourceRun`, `SourceStatus`, dan error code;
- skema respons endpoint pada SRS bagian 8;
- nama event SSE dan payload minimum;
- aturan budget reserve/reconcile;
- fixture contoh untuk success, empty, rate-limit, timeout, dan invalid payload.

Orang 3 menulis kontrak. Orang 1, 2, 4, dan 5 memberi persetujuan. Setelah Gate 0, perubahan kontrak harus mempunyai contract test dan persetujuan semua pemilik yang terdampak.

## 3. Orang 1 — YouTube & Google Maps Source Engineer

### Sasaran

Menjamin YouTube dan Google Maps menghasilkan evidence relevan, hemat kuota, tahan variasi payload, dan tidak memasukkan hiburan yang tidak terkait UMKM.

### File yang dimiliki dan dikerjakan

**Ubah:**

- `app/youtube/client.py`
- `app/youtube/errors.py`
- `app/youtube/parsing.py`
- `app/youtube/quota.py`
- `app/youtube/trend_discovery.py`
- `app/youtube/stats_snapshot.py`
- `app/youtube/trend_metrics.py`
- `app/maps/apify_client.py`
- `app/maps/collector.py`
- `app/maps/errors.py`
- `app/maps/parsing.py`
- `app/maps/relevance.py`
- `app/maps/usage.py`
- `scripts/yt_trend_probe.py`
- `scripts/maps_probe.py`
- `tests/test_apify_maps.py`
- `tests/test_discovery_v3.py`
- `tests/test_metrics_v3.py`
- `tests/test_public_youtube_v3.py`
- `tests/test_usage_v3.py` hanya bagian YouTube/Maps
- `tests/test_youtube.py`
- `tests/test_youtube_client_v3.py`
- `tests/test_youtube_parsing_v3.py`

**Buat:**

- `tests/fixtures/youtube/search_success.json`
- `tests/fixtures/youtube/video_details.json`
- `tests/fixtures/youtube/noise_results.json`
- `tests/fixtures/maps/places_success.json`
- `tests/fixtures/maps/places_empty.json`
- `tests/fixtures/maps/reviews_mixed.json`
- `tests/test_youtube_umkm_relevance.py`
- `tests/test_maps_product_opinion.py`

### Pekerjaan

1. Bekukan input/output adapter sesuai kontrak Gate 0.
2. Perketat query dan post-filter YouTube; tambahkan kasus Upin Ipin, kartun, episode, game, musik, dan query ambigu ke fixture noise.
3. Pastikan mode public dan API menghasilkan model yang sama.
4. Pastikan snapshot metrik idempotent dan delta tidak negatif karena data hilang.
5. Normalisasi Google Maps places/reviews dan simpan refresh walaupun hasil kosong.
6. Bedakan raw place, relevant place, raw review, dan relevant review dalam hasil collector.
7. Pastikan budget di-refund jika actor ditolak sebelum run dibuat.

### Tidak boleh disentuh

- `app/main.py`, `app/config.py`, `app/models.py`
- `app/api/**`
- `app/db.py`, `app/db_postgres.py`, `supabase/**`
- `app/social/**`, `app/marketplace/**`
- `app/analyzer/**`, `app/nlp/**`, `static/**`

### Acceptance criteria

- Fixture noise tidak menghasilkan video aktif.
- Query produk baru selain seed dapat menemukan hasil tanpa hardcode.
- Run Maps success/empty/error masing-masing mempunyai hasil status yang berbeda.
- Test milik Orang 1 lulus tanpa network.
- Probe manual mencetak count dan durasi tanpa mencetak token.

## 4. Orang 2 — TikTok, Instagram, Facebook & Shopee Source Engineer

### Sasaran

Menjadikan empat adapter Apify dapat dibuktikan secara operasional, memperbaiki fairness budget Facebook, dan membuat Shopee menghasilkan data atau error/empty state yang jujur.

### File yang dimiliki dan dikerjakan

**Ubah:**

- `app/social/apify_client.py`
- `app/social/collector.py`
- `app/social/errors.py`
- `app/social/parsing.py`
- `app/social/usage.py`
- `app/marketplace/apify_client.py`
- `app/marketplace/collector.py`
- `app/marketplace/errors.py`
- `app/marketplace/parsing.py`
- `app/marketplace/usage.py`
- `scripts/social_probe.py`
- `tests/test_social_apify.py`
- `tests/test_marketplace_apify.py`
- `tests/test_marketplace_ingest.py` hanya kontrak Shopee yang terkait

**Buat:**

- `scripts/marketplace_probe.py`
- `tests/fixtures/social/tiktok_success.json`
- `tests/fixtures/social/instagram_success.json`
- `tests/fixtures/social/facebook_success.json`
- `tests/fixtures/social/empty.json`
- `tests/fixtures/marketplace/shopee_success.json`
- `tests/fixtures/marketplace/shopee_variants.json`
- `tests/fixtures/marketplace/shopee_empty.json`
- `tests/test_social_budget_fairness.py`
- `tests/test_shopee_parser_variants.py`

### Pekerjaan

1. Pisahkan reservasi budget TikTok, Instagram, dan Facebook atau implementasikan round-robin yang teruji.
2. Pastikan satu platform gagal tidak menghentikan dua platform lainnya.
3. Rekonsiliasi usage pada start gagal, timeout, abort, success, dan hasil kosong.
4. Validasi input actor terhadap schema actor yang sedang dipakai.
5. Catat provider run ID, raw count, relevant count, dan alasan rejection untuk handoff ke Orang 3.
6. Perbaiki parser Facebook dan Shopee terhadap fixture payload nyata yang sudah disanitasi.
7. Batasi query, hasil, media download, komentar, dan retry agar pemakaian Apify terkendali.

### Tidak boleh disentuh

- `app/main.py`, `app/config.py`, `app/models.py`
- `app/api/**`, `app/db.py`, `app/db_postgres.py`, `supabase/**`
- `app/social/sentiment.py`
- `app/analyzer/**`, `app/nlp/**`, `static/**`

### Acceptance criteria

- Dalam simulasi enam topik, Facebook memperoleh kesempatan run yang sama dan tidak selalu menjadi platform terakhir yang kehabisan budget.
- Semua adapter menghasilkan status success, empty, budget-exhausted, dan failed yang dapat dibedakan.
- Shopee menyimpan produk dari minimal dua variasi payload fixture.
- Test milik Orang 2 lulus tanpa network.
- Probe tidak menampilkan secret atau payload author privat.

## 5. Orang 3 — Backend, Supabase & Integration Engineer

### Sasaran

Menjadi pemilik kontrak, database, scheduler, API, dan composition root; menghilangkan N+1 `/api/topics`, timeout pool, serta status aktif palsu.

### File yang dimiliki dan dikerjakan

**Ubah:**

- `app/main.py`
- `app/config.py`
- `app/models.py`
- `app/db.py`
- `app/db_postgres.py`
- `app/events.py`
- `app/topics/service.py`
- `app/youtube/trend_scheduler.py`
- seluruh `app/api/*.py`
- `index.py`
- `supabase/config.toml`
- `scripts/backup_sqlite_to_supabase.py`
- `scripts/reset_db.py`
- `tests/conftest.py`
- `tests/test_api.py`
- `tests/test_api_v3.py`
- `tests/test_postgres_backend.py`

**Buat:**

- migration melalui `supabase migration new add_source_runs` lalu edit file hasil generator di `supabase/migrations/`
- `app/api/routes_source_status.py`
- `app/api/routes_internal_refresh.py`
- `app/source_runs.py`
- `tests/test_source_runs.py`
- `tests/test_source_status_api.py`
- `tests/test_topics_query_budget.py`
- `tests/test_scheduler_isolation.py`
- `tests/test_internal_refresh.py`

### Pekerjaan

1. Definisikan model evidence/status/run dan error code pada Gate 0.
2. Tambahkan repository dan migration `source_runs`, indeks, RLS defense in depth, dan revoke schema privat.
3. Ganti query per topik pada `/api/topics` dengan agregasi bounded.
4. Atur pool Postgres dan timeout untuk serverless; jangan menjalankan DDL pada cold start production.
5. Pecah lock scheduler per `(topic, source)` dan simpan lifecycle run.
6. Tambahkan endpoint source status dan internal cron refresh.
7. Pertahankan endpoint compatibility selama contract test masih mengharuskannya.
8. Hubungkan adapter Orang 1/2 dan analyzer Orang 4 hanya di `app/main.py`.
9. Publikasikan SSE lifecycle dan lakukan sanitasi error.

### Tidak boleh disentuh

- Implementasi internal adapter `app/youtube/**` selain `trend_scheduler.py`
- `app/maps/**`, `app/marketplace/**`
- `app/social/**` selain perubahan wiring yang dilakukan di `app/main.py`
- `app/analyzer/**`, `app/nlp/**`
- `static/**`

### Acceptance criteria

- Migration fresh dan upgrade existing lulus.
- `/api/topics` tidak N+1 dan memenuhi p95 SRS.
- Timeout satu source menghasilkan run failed tanpa menghentikan source lain.
- Status health/config tidak lagi digunakan sebagai bukti operational/fresh.
- Semua response bebas secret dan stack trace.
- Seluruh test backend/integration lulus pada SQLite; test Postgres yang tersedia juga lulus.

## 6. Orang 4 — AI/NLP & Data Quality Engineer

### Sasaran

Menjamin relevansi dan sentimen Bahasa Indonesia memahami konteks, bukan sekadar mendeteksi kata negatif, serta menghasilkan insight yang dapat dijelaskan.

### File yang dimiliki dan dikerjakan

**Ubah:**

- seluruh `app/analyzer/*.py`
- seluruh `app/nlp/*.py` dan file leksikon `.txt`
- `app/social/sentiment.py`
- `app/youtube/content_type.py`
- `app/api/routes_summary.py` hanya melalui perubahan yang direview Orang 3
- `tests/test_content_type_v3.py`
- `tests/test_gemini_parse.py`
- `tests/test_keywords.py`
- `tests/test_lexicon.py`
- `tests/test_preprocess.py`
- `tests/test_worker.py`

**Buat:**

- `tests/fixtures/nlp/sentiment_id.json`
- `tests/fixtures/nlp/relevance_id.json`
- `tests/fixtures/nlp/content_type_id.json`
- `tests/test_sentiment_indonesian_context.py`
- `tests/test_social_relevance.py`
- `tests/test_gemini_fallback.py`
- `docs/AI_EVALUATION.md`

### Pekerjaan

1. Susun golden set minimal 150 contoh: positif, negatif, netral, promosi, slang, emoji, negasi, pertanyaan retoris, dan ambigu.
2. Pisahkan relevansi produk dari sentimen; post tidak relevan tidak boleh dipaksa memiliki sentimen produk.
3. Perketat schema output Gemini, parsing, batching, rate limit, retry, cooldown, dan fallback.
4. Pastikan analyzer dan model yang dipakai tercatat per evidence.
5. Buat evaluasi macro-F1 dan confusion matrix; target awal macro-F1 minimal 0,80 pada golden set yang dibekukan.
6. Pastikan insight menyebut periode dan jumlah evidence, serta tidak membuat klaim ketika data sedikit.

### Tidak boleh disentuh

- Adapter/provider dan usage tracker
- `app/main.py`, `app/config.py`, `app/models.py`
- `app/db.py`, `app/db_postgres.py`, `supabase/**`
- `static/**`

### Acceptance criteria

- Dua contoh salah klasifikasi yang dilaporkan pengguna menjadi positif atau netral sesuai konteks.
- Parser Gemini menolak label/aspek di luar schema.
- Fallback deterministik dan diberi label analyzer yang benar.
- Golden set, metrik, keterbatasan, dan cara reproduksi terdokumentasi.
- Semua test AI/NLP lulus tanpa API Gemini sungguhan.

## 7. Orang 5 — Frontend, UX, QA & Deployment Engineer

### Sasaran

Menyediakan dashboard source-first yang cepat, jujur terhadap status proses, responsif, mudah didemokan, dan terverifikasi di production.

### File yang dimiliki dan dikerjakan

**Ubah:**

- seluruh `static/*.html`, `static/*.css`, dan `static/*.js`
- seluruh `design/**`
- `vercel.json`
- `.vercelignore`
- `.env.example` untuk dokumentasi nama variable, tanpa secret
- `README.md`

**Buat:**

- `tests/e2e/test_dashboard_sources.py`
- `tests/e2e/test_dashboard_states.py`
- `tests/e2e/test_dashboard_responsive.py`
- `scripts/production_smoke.py`
- `docs/OPERATOR_RUNBOOK.md`
- `docs/DEMO_SCRIPT.md`
- `docs/RELEASE_CHECKLIST.md`

Jika browser E2E memerlukan dependency baru, perubahan `requirements-dev.txt` hanya boleh berisi dependency development yang dipin; `requirements.txt` runtime tidak boleh bertambah.

### Pekerjaan

1. Implementasikan sidebar terpisah untuk enam source plus Ringkasan.
2. Hubungkan status operasional, freshness, count, dan progress tanpa menafsirkan `configured` sebagai aktif.
3. Pertahankan snapshot lama selama request baru berlangsung.
4. Buat loading, empty, filter-empty, budget, stale, dan error state yang berbeda.
5. Batasi request berdasarkan source aktif; perubahan filter YouTube tidak boleh me-refresh source lain.
6. Uji keyboard, focus, kontras, desktop, tablet, mobile, reconnect SSE, dan race saat pindah topik.
7. Siapkan smoke production dan runbook rollback.

### Tidak boleh disentuh

- `app/**`, `supabase/**`, dan adapter provider
- test unit backend milik Orang 1–4
- secret atau nilai environment production

### Acceptance criteria

- Seluruh navigasi source dan state dapat diuji dari mock API.
- Tidak ada panel kosong tanpa alasan/progress.
- Tidak ada console error, page error, atau horizontal overflow.
- API request tidak berulang tanpa batas dan request lama tidak menimpa topik baru.
- Production smoke memverifikasi halaman dan endpoint semua source.

## 8. Matriks kepemilikan singkat

| Area | Pemilik | Reviewer utama |
|---|---:|---:|
| `app/youtube/**`, `app/maps/**` | 1 | 3 |
| `app/social/**` kecuali sentiment, `app/marketplace/**` | 2 | 3 |
| `app/main.py`, config, model, DB, API, scheduler, migration | 3 | 1/2/4 sesuai kontrak |
| analyzer, NLP, social sentiment, content classifier | 4 | 3 |
| static, design, E2E, deploy docs | 5 | 3 |
| runtime dependencies | 3 | 1/2/4 |
| development dependencies | 5 | 3 |
| SRS dan kontrak API | 3 | semua |

## 9. Urutan pull request

1. **PR-0 Orang 3:** kontrak model/API/event dan test skeleton.
2. **PR-1 Orang 3:** migration `source_runs`, repository, query agregat.
3. **PR-2 Orang 1:** YouTube + Maps adapter dan fixture.
4. **PR-3 Orang 2:** social + Shopee adapter, parser, fairness.
5. **PR-4 Orang 4:** relevance, sentiment, golden evaluation.
6. **PR-5 Orang 3:** scheduler/wiring/API integration.
7. **PR-6 Orang 5:** dashboard terhadap kontrak final dan E2E.
8. **PR-7 Orang 5 + Orang 3:** deployment, smoke, dan release evidence.

PR-2, PR-3, dan PR-4 dapat berjalan paralel setelah PR-0. PR-5 baru digabung setelah ketiganya stabil. PR-6 dapat mulai dengan mock setelah PR-0, tetapi integrasi final menunggu PR-5.

## 10. Rencana 10 hari kerja

| Hari | Orang 1 | Orang 2 | Orang 3 | Orang 4 | Orang 5 |
|---|---|---|---|---|---|
| 1 | Review kontrak | Review kontrak | Tulis Gate 0 | Review kontrak | Mock UI dari kontrak |
| 2–3 | Fixture + adapter YT | Fixture + adapter sosial | Migration + repository | Golden set | Sidebar + states |
| 4 | Maps | Budget fairness | Query agregat | Gemini/fallback | API state layer |
| 5 | Test error/empty | Shopee parser | Source status API | Evaluasi | Responsive/a11y |
| 6 | Probe + dokumentasi | Probe + dokumentasi | Scheduler isolation | Insight | E2E mock |
| 7 | Fix integrasi | Fix integrasi | Wiring semua modul | Fix integrasi | Integrasi live |
| 8 | Regression | Regression | Performance/DB | Regression | E2E lengkap |
| 9 | Review silang | Review silang | Staging deploy | Review hasil | Visual QA/smoke |
| 10 | Bugfix | Bugfix | Production/rollback | Validasi AI | Demo/release checklist |

## 11. Definition of done tim

- Clean clone dapat dijalankan mengikuti README.
- Test default offline lulus dan tidak memakai credential nyata.
- Migration dapat direproduksi pada database kosong.
- Enam source mempunyai status operasional yang dapat dibuktikan.
- Facebook tidak kelaparan karena urutan budget.
- Shopee tidak lagi tampil aktif ketika tidak menghasilkan produk.
- Sentimen Bahasa Indonesia lulus golden set yang dibekukan.
- Dashboard menjaga snapshot saat background refresh.
- Production smoke, visual QA, performance check, dan secret scan lulus.
- Setiap PR mempunyai ringkasan, test evidence, risiko, dan langkah rollback.
