# Software Requirements Specification (SRS)

## Pemantau Tren & Opini UMKM — versi 4.0 POC

| Atribut | Nilai |
|---|---|
| Status | Baseline implementasi dan acuan rebuild |
| Tanggal | 2 Oktober 2026 |
| Bahasa UI | Bahasa Indonesia |
| Backend | Python, FastAPI, async HTTP |
| Database | Supabase Postgres di production, SQLite untuk development/test |
| Frontend | HTML, CSS, dan JavaScript tanpa build step |
| Sumber production | YouTube, Google Maps, TikTok, Instagram, Facebook, Shopee |

Dokumen ini adalah sumber kebenaran requirement untuk pekerjaan berikutnya. Implementasi baru wajib mempertahankan fitur yang sudah tersedia dan memperbaiki status sumber yang saat ini hanya membedakan “dikonfigurasi” dan “tidak dikonfigurasi”. Context operasional ringkas ada di `docs/TEAM_CONTEXT_4_ORANG.md`.

## 1. Tujuan produk

Aplikasi membantu pelaku UMKM menjawab tiga pertanyaan untuk satu produk:

1. Apakah produk sedang memperoleh perhatian publik?
2. Apa pendapat pelanggan dan pembuat konten tentang produk tersebut?
3. Peluang inovasi apa yang dapat ditindaklanjuti berdasarkan bukti yang dapat dibuka kembali?

Aplikasi tidak boleh menyebut data sebagai “live” hanya karena API key tersedia. Status aktif harus dibuktikan oleh keberhasilan refresh, timestamp, dan jumlah evidence yang tersimpan.

## 2. Ruang lingkup

### 2.1 Termasuk

- Watchlist maksimal 20 topik produk, tidak dikunci pada kategori tertentu.
- Sinyal tren YouTube berupa video, views, pertumbuhan views, engagement, dan jenis konten.
- Opini lokasi Google Maps berupa tempat, rating, jumlah ulasan, dan ulasan yang menyebut produk.
- Sinyal sosial TikTok, Instagram, dan Facebook berupa caption/post, engagement, waktu publikasi, relevansi, dan sentimen.
- Sinyal marketplace Shopee berupa produk, harga, rating, jumlah rating, sold count, dan toko jika provider menyediakannya.
- Analisis sentimen Bahasa Indonesia kontekstual: positif, negatif, netral, atau pending.
- Ekstraksi aspek seperti rasa, harga, tekstur, kualitas, kemasan, pelayanan, dan lokasi.
- Dashboard source-first: Ringkasan, TikTok, Instagram, Facebook, Google Maps, YouTube, dan Shopee.
- Snapshot-first loading, refresh background, SSE, status proses, kontrol kuota, retry terbatas, dan penyimpanan persisten.
- Production deployment di Vercel dengan Supabase Postgres.

### 2.2 Compatibility yang dipertahankan

- Endpoint feed/statistik v2 dan Chrome Review Bridge tetap berjalan selama belum ada keputusan penghapusan terpisah.
- SQLite tetap tersedia untuk test dan development offline.
- Play Store, replay, dan inbox tetap compatibility/manual-only; tidak boleh muncul sebagai source production aktif.

### 2.3 Tidak termasuk

- Login pengguna, pembayaran, multi-tenant, dan aplikasi mobile native.
- Bypass CAPTCHA, login marketplace, stealth browser, atau pelanggaran batas provider.
- Klaim bahwa caption promosi adalah ulasan pelanggan.
- Komentar YouTube sebagai sumber opini produk.
- Tokopedia dan TikTok Shop sebagai crawler server production. Keduanya hanya boleh masuk melalui Review Bridge sampai ada integrasi resmi yang disetujui.

## 3. Pengguna dan use case

### 3.1 Pengguna utama

- Pemilik UMKM: memilih produk dan membaca ringkasan.
- Analis/peserta kompetisi: menelusuri evidence dan menjelaskan metodologi.
- Operator: memantau kuota, error, freshness, dan deployment.

### 3.2 Use case utama

| ID | Use case | Hasil |
|---|---|---|
| UC-01 | Menambah produk pantauan | Topik langsung tersimpan dan refresh dijadwalkan |
| UC-02 | Membuka topik | Snapshot lama tampil lebih dahulu tanpa menunggu provider |
| UC-03 | Memilih sumber | Hanya panel sumber tersebut yang ditampilkan dan dimuat |
| UC-04 | Melihat feed | Evidence memiliki platform, tanggal, URL, dan metrik |
| UC-05 | Melihat sentimen | Jumlah, tren harian, aspek, dan status analyzer terlihat |
| UC-06 | Memeriksa sumber | Status membedakan config, running, fresh, empty, error, dan limit |
| UC-07 | Memantau biaya | Pemakaian harian/bulanan dan sisa budget terlihat per provider |
| UC-08 | Refresh gagal | Snapshot lama tetap terlihat, disertai error dan waktu percobaan |

## 4. Arsitektur logis

```text
Browser
  ├─ GET snapshot API ───────────────┐
  └─ SSE status/progress             │
                                     ▼
FastAPI ── topic/source services ── Supabase Postgres
  │                                  ▲
  ├─ YouTube adapter                 │ upsert evidence + source_runs
  ├─ Google Maps Apify adapter       │
  ├─ TikTok Apify adapter            │
  ├─ Instagram Apify adapter         │
  ├─ Facebook Apify adapter          │
  ├─ Shopee Apify adapter            │
  └─ Gemini/lexicon analyzer ────────┘
```

Prinsip wajib:

- Endpoint baca tidak menjalankan scraping.
- Refresh provider terjadi sebagai pekerjaan background yang dapat dilacak.
- Setiap adapter mengeluarkan kontrak evidence yang dinormalisasi.
- Database menjadi sumber kebenaran untuk snapshot, freshness, dan status run.
- API key dan connection string hanya berada di server.

## 5. Definisi status sumber

Setiap source harus memiliki status berikut, global dan per topik:

| Status | Arti |
|---|---|
| `disabled` | Tidak ada di `SOURCES` |
| `misconfigured` | Source aktif tetapi credential/provider belum lengkap |
| `queued` | Refresh sudah dijadwalkan |
| `running` | Provider sedang dipanggil |
| `fresh` | Run terakhir berhasil dan snapshot belum melewati TTL |
| `empty` | Run berhasil tetapi provider/filter menghasilkan nol evidence |
| `stale` | Ada snapshot, tetapi melewati interval refresh |
| `budget_exhausted` | Run tidak dimulai karena batas aplikasi/provider |
| `error` | Run gagal; pesan aman dan dapat ditindaklanjuti tersedia |

`configured=true` tidak boleh diterjemahkan sebagai `fresh`. Badge hijau hanya dipakai untuk `fresh`; `empty`, `budget_exhausted`, dan `error` mempunyai tampilan berbeda.

## 6. Persyaratan fungsional

### 6.1 Topik

- **FR-TOP-01** — Pengguna dapat membuat topik dari nama, kategori, kota, keyword, product terms, dan exclude terms.
- **FR-TOP-02** — Slug topik unik, stabil, dan aman dipakai sebagai ID URL/API.
- **FR-TOP-03** — Maksimum topik aktif berasal dari konfigurasi server.
- **FR-TOP-04** — Menonaktifkan topik tidak menghapus evidence historis tanpa tindakan eksplisit.
- **FR-TOP-05** — Daftar topik mengembalikan semua count dalam query yang jumlahnya tetap, bukan query per topik.

### 6.2 Kontrak evidence

Semua evidence minimal memiliki:

- `source`, `external_id`, `topic_id`, `url`;
- `title` atau `text`;
- `published_at`, `first_seen_at`, `last_seen_at`;
- `query`, `mentions_product`, dan alasan/score relevansi;
- metrik provider yang tersedia tanpa mengarang nilai yang tidak ada.

- **FR-EVD-01** — Upsert harus idempotent berdasarkan source, external ID, dan topic.
- **FR-EVD-02** — Evidence yang tidak relevan tidak ditampilkan sebagai opini produk.
- **FR-EVD-03** — Nilai provider yang tidak tersedia disimpan sebagai `null`, bukan nol.
- **FR-EVD-04** — URL evidence dapat dibuka dari dashboard.

### 6.3 YouTube

- **FR-YT-01** — Mendukung YouTube Data API ketika key tersedia dan mode publik ketika key kosong.
- **FR-YT-02** — Query wajib memakai nama/keyword produk dan exclude terms UMKM untuk menolak kartun, episode, game, musik, dan noise serupa.
- **FR-YT-03** — Video diklasifikasikan menjadi review, resep/cara pakai, ide usaha, atau lainnya.
- **FR-YT-04** — Statistik video disnapshot agar delta views 24 jam dan views/hari dapat dihitung.
- **FR-YT-05** — Dashboard menampilkan mode `api` atau `public` secara jujur.

### 6.4 Google Maps

- **FR-MAP-01** — Pencarian menggunakan produk dan kota melalui actor Google Maps yang dikonfigurasi.
- **FR-MAP-02** — Tempat disimpan hanya jika relevan terhadap produk/kategori.
- **FR-MAP-03** — Feed opini hanya memuat ulasan yang menyebut produk atau istilah produknya.
- **FR-MAP-04** — Tempat tanpa ulasan relevan tetap boleh muncul sebagai pesaing, tetapi tidak menambah jumlah opini.
- **FR-MAP-05** — Timestamp refresh per topik tersimpan walaupun hasil run kosong.

### 6.5 TikTok, Instagram, dan Facebook

- **FR-SOC-01** — Ketiga platform mempunyai adapter, checkpoint, status, dan budget masing-masing.
- **FR-SOC-02** — Budget tidak boleh membuat platform terakhir selalu kelaparan. Scheduler harus round-robin atau memakai cap per platform.
- **FR-SOC-03** — Caption/post difilter berdasarkan product terms sebelum masuk analisis tren dan sentimen.
- **FR-SOC-04** — Platform dapat menghasilkan status `empty` tanpa dianggap error.
- **FR-SOC-05** — Feed dan statistik dapat difilter per platform.
- **FR-SOC-06** — Post promosi, pertanyaan retoris, slang, emoji, dan negasi Bahasa Indonesia dianalisis berdasarkan konteks kalimat.

### 6.6 Shopee

- **FR-SHP-01** — Actor Shopee berjalan dengan satu query bounded per topic dan tidak memblokir request GET.
- **FR-SHP-02** — Produk dinormalisasi menjadi judul, toko, URL, harga, harga asli, rating, rating count, sold count, stock, dan gambar.
- **FR-SHP-03** — Parser mendukung variasi payload actor dan mencatat alasan ketika semua item ditolak.
- **FR-SHP-04** — Run yang gagal sebelum actor dimulai tidak dihitung sebagai pemakaian sukses.
- **FR-SHP-05** — Nol produk ditampilkan sebagai `empty` beserta waktu run, bukan badge aktif palsu.

### 6.7 Sentimen dan insight

- **FR-AI-01** — Label yang sah: `positif`, `negatif`, `netral`, `pending`.
- **FR-AI-02** — Gemini menjadi analyzer utama ketika sehat; fallback leksikon ditandai jelas.
- **FR-AI-03** — Output terstruktur memuat label, score -1..1, aspek, confidence, dan alasan singkat.
- **FR-AI-04** — Contoh “Siapa sih yang nggak suka es satu ini” harus positif, bukan negatif.
- **FR-AI-05** — Narasi “akhirnya produk ini kelihatan lagi” tidak boleh negatif hanya karena kata “akhirnya”.
- **FR-AI-06** — Caption yang hanya mengumumkan produk tanpa evaluasi adalah netral.
- **FR-AI-07** — Analisis dibatch, rate-limited, retry terbatas, dan hasilnya disimpan agar tidak dianalisis ulang.
- **FR-AI-08** — Ringkasan dan ide inovasi selalu menyebut jumlah evidence dan periode yang dipakai.

### 6.8 Refresh, live feed, dan kuota

- **FR-RUN-01** — Setiap refresh membuat satu record `source_runs`.
- **FR-RUN-02** — Lock berlaku per `(topic_id, source)` agar source lain tetap dapat berjalan.
- **FR-RUN-03** — Status/progress dikirim lewat SSE dan disimpan untuk reconnect.
- **FR-RUN-04** — Snapshot lama tidak dikosongkan selama refresh.
- **FR-RUN-05** — Retry hanya untuk timeout, rate limit, dan error 5xx; maksimum tiga percobaan dengan backoff.
- **FR-RUN-06** — Budget direservasi tepat sebelum provider dipanggil dan direkonsiliasi setelah selesai/gagal.
- **FR-RUN-07** — UI menampilkan pemakaian harian dan bulanan untuk Maps, setiap platform sosial, dan Shopee.
- **FR-RUN-08** — Production refresh dijalankan oleh job/cron yang bounded; request halaman tidak bergantung pada loop background serverless yang panjang.

### 6.9 Dashboard

- **FR-UI-01** — Sidebar sumber: Ringkasan, TikTok, Instagram, Facebook, Google Maps, YouTube, Shopee.
- **FR-UI-02** — Header selalu menampilkan topik, periode, freshness, dan status sumber aktif.
- **FR-UI-03** — Loading state menyebut tahap: membaca snapshot, antre, mengambil provider, menyaring, menganalisis, atau selesai.
- **FR-UI-04** — Empty state membedakan belum pernah refresh, hasil valid nol, filter nol, budget habis, dan error.
- **FR-UI-05** — Setiap kartu evidence menampilkan platform, waktu, teks/judul, sentimen bila relevan, metrik, dan tautan sumber.
- **FR-UI-06** — Desktop, tablet, dan mobile tidak memiliki horizontal overflow.
- **FR-UI-07** — Navigasi keyboard, focus state, label form, dan kontras memenuhi WCAG 2.1 AA untuk alur utama.

## 7. Model data

Tabel yang dipertahankan:

- `scraper.topics`
- `scraper.videos`, `scraper.video_stats`
- `scraper.places`, `scraper.place_snapshots`, `scraper.comments`
- `scraper.social_posts`, `scraper.social_post_stats`, `scraper.social_refreshes`
- `scraper.marketplace_products`, `scraper.marketplace_refreshes`
- `scraper.summaries`, `scraper.api_usage`

Tabel baru yang diwajibkan untuk status operasional:

```sql
create table scraper.source_runs (
    id bigint generated always as identity primary key,
    topic_id text references scraper.topics(id) on delete cascade,
    source text not null,
    status text not null,
    trigger text not null,
    query_count integer not null default 0,
    raw_count integer,
    relevant_count integer,
    inserted_count integer,
    reserved_units integer not null default 0,
    billed_units integer,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    provider_run_id text,
    error_code text,
    error_message text,
    check (status in ('queued','running','succeeded','empty','budget_exhausted','failed'))
);
```

Indeks minimal:

- `(topic_id, source, started_at desc)` untuk status terbaru;
- partial index run `queued/running` untuk lock/recovery;
- indeks feed berdasarkan topic, platform/source, dan waktu turun;
- indeks pending sentiment berdasarkan status dan waktu.

Schema `scraper` tetap privat dan bukan Data API publik. Migration dibuat melalui workflow Supabase, direview, lalu dijalankan sebelum deployment. Runtime production tidak menjalankan DDL. RLS tetap diaktifkan sebagai defense in depth, dan `anon`/`authenticated` tidak mendapat akses schema privat.

## 8. Kontrak API

Endpoint baca yang wajib:

| Method | Endpoint | Tujuan |
|---|---|---|
| GET | `/api/health` | Liveness, backend, dan konfigurasi; bukan bukti data aktif |
| GET | `/api/sources/status?topic_id=` | Status operasional setiap source |
| GET | `/api/usage` | Budget dan pemakaian per source |
| GET | `/api/topics` | Topik dan count agregat |
| GET | `/api/trend` | Metrik YouTube |
| GET | `/api/trend/videos` | Evidence video |
| GET | `/api/maps/places` | Tempat/pesaing |
| GET | `/api/maps/feed` | Opini Google Maps |
| GET | `/api/social/feed` | Post sosial dengan filter platform |
| GET | `/api/social/stats` | Sentimen/aspek sosial |
| GET | `/api/marketplace/products` | Produk Shopee |
| GET | `/api/marketplace/stats` | Statistik Shopee |
| GET | `/api/stream` | SSE progress dan evidence baru |

Endpoint mutasi:

| Method | Endpoint | Aturan |
|---|---|---|
| POST | `/api/topics` | Validasi dan jadwalkan refresh |
| POST | `/api/topics/suggest` | Saran keyword bounded |
| DELETE | `/api/topics/{id}` | Soft deactivate |
| POST | `/api/internal/refresh` | Hanya cron/operator dengan secret server |
| POST | `/api/ingest/marketplace` | Compatibility Review Bridge dengan token/CORS ketat |

Contoh respons status:

```json
{
  "topic_id": "seblak",
  "sources": [
    {
      "source": "facebook",
      "configured": true,
      "state": "budget_exhausted",
      "last_attempt_at": "2026-10-02T10:00:00Z",
      "last_success_at": null,
      "evidence_count": 0,
      "message": "Batas Facebook hari ini tercapai"
    }
  ]
}
```

Pesan error yang dikirim ke browser tidak boleh memuat token, DSN, stack trace, atau payload privat provider.

## 9. Event SSE

Event minimum:

- `source_run_started`
- `source_run_progress`
- `source_run_completed`
- `source_run_failed`
- `trend_tick`
- `social_post_new`
- `social_sentiment_updated`
- `marketplace_product_new`

Semua event memiliki `topic_id`, `source`, `occurred_at`, dan payload count. Client harus reconnect dengan backoff dan selalu melakukan reconciliation melalui GET setelah reconnect.

## 10. Persyaratan nonfungsional

### 10.1 Kinerja

- **NFR-PERF-01** — `/api/health` p95 di bawah 500 ms tanpa provider call.
- **NFR-PERF-02** — `/api/topics` p95 di bawah 1,5 detik pada 20 topik dan tidak melakukan pola N+1.
- **NFR-PERF-03** — Endpoint snapshot p95 di bawah 1 detik setelah koneksi database hangat.
- **NFR-PERF-04** — Halaman menampilkan shell/loading bermakna di bawah 1 detik dan snapshot pertama di bawah 2,5 detik pada koneksi normal.
- **NFR-PERF-05** — Provider call tidak berada di critical path render dashboard.

### 10.2 Reliabilitas

- Upsert dan checkpoint idempotent.
- Satu kegagalan source tidak menggagalkan source lain.
- Timeout database/provider menghasilkan status run final, bukan `running` selamanya.
- Pool Postgres disetel konservatif untuk serverless dan semua acquire mempunyai timeout.
- Run yang terputus direkonsiliasi menjadi failed/stale oleh job berikutnya.

### 10.3 Keamanan dan privasi

- Tidak ada secret di source, browser, log, response, screenshot, atau fixture.
- Token yang pernah dibagikan melalui chat harus dirotasi sebelum penggunaan production jangka panjang.
- Author/customer identifier tidak disimpan kecuali diperlukan; gunakan HMAC server untuk deduplikasi jika identifier stabil wajib dipakai.
- URL eksternal disanitasi dan hanya skema HTTP/HTTPS yang ditampilkan.
- Endpoint internal dan ingest menggunakan secret yang berbeda.

### 10.4 Maintainability

- Fungsi dan modul baru memiliki type hints.
- Adapter provider tidak mengakses HTML/UI.
- Intelligence murni tidak mengakses network/database.
- API tidak mengetahui detail payload mentah provider.
- Test default tidak memanggil API sungguhan.

## 11. Observability

Log terstruktur minimum:

- `request_id`, `topic_id`, `source`, `run_id`, `provider_run_id`;
- durasi queue, provider, parse/filter, database, dan analysis;
- raw/relevant/inserted count;
- error code yang stabil dan pesan aman.

Dashboard operator harus dapat membedakan:

- provider tidak dikonfigurasi;
- budget aplikasi habis;
- hard limit provider habis;
- provider berhasil tetapi hasil kosong;
- semua hasil ditolak filter;
- database timeout;
- analyzer pending atau gagal.

## 12. Strategi test

### 12.1 Unit

- Parser setiap source memakai fixture provider.
- Relevance filter dan classifier memakai golden dataset.
- Budget reservation/refund dan pembagian adil per platform.
- Sentimen Bahasa Indonesia, negasi, slang, retoris, promosi, dan netral.
- Trend metrics dan agregat deterministik.

### 12.2 Integration

- Fresh SQLite dan fresh Postgres migration.
- `collect → parse → filter → upsert → API` dengan fake provider.
- Scheduler multi-source: error satu source tidak menghentikan yang lain.
- Query-count assertion untuk `/api/topics`.
- SSE start/progress/complete/error.

### 12.3 Browser/E2E

- Pilih setiap source dan setiap topik.
- Snapshot tetap ada ketika refresh berjalan.
- Empty/error/budget/loading/fresh state.
- Desktop 1440 px, tablet 768 px, dan mobile 390 px.
- Tidak ada console error, request loop, atau horizontal overflow.

### 12.4 Production smoke

- `/`, `/api/health`, `/api/topics`, `/api/usage` HTTP 200.
- Satu endpoint evidence per source dapat dibaca tanpa memicu run baru.
- Status setiap source sesuai bukti database.
- Tidak ada secret di HTML/JavaScript/JSON.

## 13. Acceptance criteria release

Release diterima jika:

1. Seluruh test unit/integration lulus offline.
2. Migration database kosong dan database existing sama-sama lulus.
3. Enam source ada di konfigurasi production.
4. Source hanya berlabel fresh bila ada run sukses dalam TTL.
5. YouTube, Maps, TikTok, dan Instagram mempertahankan evidence yang sudah berjalan.
6. Facebook menghasilkan post atau status empty/error yang dapat dibuktikan, bukan status aktif palsu.
7. Shopee menghasilkan produk atau status empty/error yang dapat dibuktikan, bukan status aktif palsu.
8. Pembagian budget tidak membuat Facebook selalu menjadi platform terakhir yang gagal.
9. `/api/topics` memenuhi batas kinerja dan tidak timeout pool Postgres.
10. Dashboard source-first lulus QA desktop dan mobile.
11. Gemini lulus golden set Bahasa Indonesia yang disepakati.
12. Production smoke dan log review bersih dari secret serta exception tak tertangani.

## 14. Urutan implementasi

1. Bekukan kontrak evidence, status, API, dan event.
2. Tambahkan `source_runs`, repository, dan query agregat.
3. Stabilkan enam adapter dan budget fairness.
4. Perbaiki relevance/sentiment dengan golden set.
5. Hubungkan dashboard ke source status dan progress.
6. Tambahkan integration/E2E/performance test.
7. Deploy migration, backend, lalu frontend.
8. Jalankan production smoke dan catat evidence release.

Pembagian kepemilikan file, urutan PR, dan output setiap orang dijelaskan dalam [docs/TEAM_CONTEXT_4_ORANG.md](docs/TEAM_CONTEXT_4_ORANG.md).
