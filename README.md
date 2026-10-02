# Pemantau Tren & Opini UMKM

Dokumen implementasi utama: [SRS v4](SRS.md). Pembagian rebuild lima orang dan kepemilikan file tersedia di [docs/REBUILD_ASSIGNMENTS.md](docs/REBUILD_ASSIGNMENTS.md).

POC v3 membantu UMKM membaca dua sinyal yang berbeda:

- **YouTube untuk tren produk** — pasokan video, pertumbuhan views, format konten, dan sinyal persaingan.
- **Google Maps untuk opini pelanggan** — tempat, rating, ulasan produk, dan pesaing lokal.
- **TikTok + Instagram untuk sinyal konten** — post publik, caption, engagement, dan creator signal dari keyword/hashtag.
- **Facebook + Shopee untuk variasi sinyal UMKM** — post publik Facebook untuk sentimen dan katalog produk Shopee Indonesia untuk harga, rating, serta sold count bila tersedia.

Implementasi saat ini mencakup **P3/M3 + Maps/Social/Marketplace POC**: fondasi data dan kuota, discovery YouTube, snapshot metrik, live ticker SSE, dashboard tren, kolektor opini Google Maps, discovery TikTok/Instagram/Facebook, serta discovery Shopee melalui Apify. Token Apify dapat dipisah per layanan atau memakai satu `APIFY_TOKEN` sebagai fallback; sumber tanpa token secara jujur ditampilkan belum dikonfigurasi.

## Jalankan dalam kurang dari 10 menit

Butuh Python 3.11 atau lebih baru.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/reset_db.py
uvicorn app.main:app --reload
```

Buka [http://127.0.0.1:8000](http://127.0.0.1:8000). Tiga topik awal tersedia: Cappuccino Cincau, Kopi Susu Gula Aren, dan Seblak. Tombol **Pantau produk** menerima produk lain seperti keripik pisang, parfum lokal, atau es teh jumbo; tidak ada kata kunci yang dikunci ke “sepatu”.

### Deploy ke Vercel (POC)

Vercel mengenali `index.py` sebagai entrypoint FastAPI. Deploy dari root repo dengan `npx vercel --prod`, lalu isi Environment Variables `APIFY_MAPS_TOKEN`, `APIFY_SOCIAL_TOKEN`, `APIFY_MARKETPLACE_TOKEN`, `SOURCES=youtube_trend,maps,tiktok,instagram,facebook,shopee`, dan `SUPABASE_DB_URL` pada project Vercel. `APIFY_TOKEN` tetap dapat dipakai sebagai fallback tunggal. Gunakan connection string Supavisor/session pooler yang server-side. Jika database URL kosong, aplikasi kembali memakai SQLite `/tmp` yang bersifat sementara.

`index.py` sengaja tidak menjalankan loop scheduler permanen di function serverless. Refresh otomatis untuk topik yang baru dibuat tetap dijalankan sebagai background task terbatas; retry operasional Facebook/Shopee memakai `POST /api/internal/refresh` dengan header `X-Refresh-Token`. Ini mencegah beberapa cold start menulis row dan membelanjakan run Apify yang sama secara bersamaan.

### Supabase MCP

Repo ini menyertakan `.mcp.json` untuk Supabase MCP yang dibatasi ke project `itbzozqigakvotvadreb`. OAuth MCP sudah dikonfigurasi lewat Codex CLI; muat ulang sesi agar tools Supabase muncul. Konfigurasi tidak menyimpan API key, password database, atau service-role secret.

MCP dipakai untuk pengelolaan dan inspeksi, bukan sebagai koneksi runtime scraper. Runtime memakai `SUPABASE_DB_URL` hanya di server. Tabel dibuat di schema privat `scraper`, sehingga tidak diekspos ke Data API `public`.

Migration dijalankan melalui Supabase MCP/CLI. `DATABASE_AUTO_MIGRATE` harus tetap `false` di Vercel agar cold start paralel tidak menjalankan DDL yang sama secara bersamaan.

Backup SQLite yang ada ke Supabase bersifat additive dan transactional:

```bash
source .venv/bin/activate
python scripts/backup_sqlite_to_supabase.py --dry-run
SUPABASE_DB_URL='postgresql://...' python scripts/backup_sqlite_to_supabase.py
```

Baris remote yang sudah ada tidak dihapus atau ditimpa. Setelah backup terverifikasi, set `DATABASE_BACKEND=postgres` dan `SUPABASE_DB_URL` di Vercel agar Supabase menjadi sumber data utama.

## Data live dan kejujuran sumber

Dashboard tidak memakai data demo untuk Panel A.

- Jika `YOUTUBE_API_KEY` diisi, aplikasi memakai YouTube Data API v3 resmi. Discovery menggunakan `search.list`, sedangkan snapshot views memakai `videos.list`.
- Jika key kosong, POC memakai halaman pencarian dan halaman video YouTube yang publik. Angka views dibaca ulang pada snapshot berikutnya. Mode ini tetap data nyata, tetapi bersifat **best effort** dan lebih mudah berubah dibanding API resmi.
- Komentar YouTube sengaja dimatikan (`YT_COMMENTS_ENABLED=false`). Komentar video sering membahas kreator/tutorial, bukan pengalaman terhadap produk.
- Angka tren adalah sampel hasil pencarian, bukan seluruh YouTube. Produk niche memang dapat menunjukkan kenaikan kecil atau tidak ada video; aplikasi tidak mengarang angka untuk mengisi grafik.
- Jika `APIFY_TOKEN` diisi, server menjalankan Actor `compass~crawler-google-places`, menunggu status `SUCCEEDED`, lalu mengambil dataset ulasan terbaru. Hasilnya difilter berdasarkan nama/kata produk sebelum masuk feed opini.
- Jika token kosong, tidak ada data Maps/TikTok/Instagram/Facebook/Shopee sintetis yang dibuat; health API menampilkan sumber Apify belum dikonfigurasi.
- TikTok dan Instagram dikumpulkan dalam satu Actor run per platform/topik. Maksimal tiga keyword/hashtag digabung, sampai 50 post per query, lalu filter umur dan relevansi dilakukan lokal. Download video, thumbnail, avatar, transkripsi, AI description, dan crawl komentar dimatikan default.
- Caption sosial yang lolos relevansi dianalisis menjadi positif, negatif, atau netral memakai analyzer Gemini yang dikonfigurasi dan fallback leksikon lokal. Statistik harian, aspek dominan, dan label per post ditampilkan di dashboard.
- Facebook memakai Actor pencarian post publik dengan maksimal 25 hasil/query. Shopee memakai Actor keyword Indonesia dengan `fetchDetail=false` agar pengumpulan katalog tetap ringan; parser menyimpan hanya produk yang menyebut kata produk yang dipantau. Field yang tidak disediakan Actor tetap ditampilkan sebagai kosong, bukan dibuat-buat.

Uji satu kata produk tanpa mengubah database utama:

```bash
source .venv/bin/activate
python scripts/yt_trend_probe.py "cappuccino cincau"
python scripts/yt_trend_probe.py "keripik pisang"
python scripts/maps_probe.py "sepatu lokal" --city Bandung
python scripts/social_probe.py "sepatu lokal" --platform tiktok
python scripts/social_probe.py "sepatu lokal" --platform instagram
python scripts/social_probe.py "sepatu lokal" --platform facebook
```

Probe YouTube mencetak query, jumlah kandidat/relevan, komposisi konten, video teratas, dan unit API yang dipakai. Probe Maps menjalankan satu Actor Apify dan hanya mencetak ringkasan tempat relevan. Probe sosial menjalankan satu Actor per platform dan mencetak post relevan tanpa menulis ke database utama; tanpa token probe berhenti sebelum mengirim request.

## Konfigurasi utama

Semua key hanya dibaca dari `.env`; jangan masukkan key ke source code atau commit `.env`.

| Variabel | Default | Fungsi |
|---|---:|---|
| `SOURCES` | `youtube_trend,maps,tiktok,instagram,facebook,shopee` | Sumber yang disiapkan aplikasi |
| `YOUTUBE_API_KEY` | kosong | Key server YouTube Data API v3; kosong memakai mode publik |
| `YT_TREND_LOOKBACK_DAYS` | `90` | Batas umur video aktif |
| `YT_SEARCH_DATE_PAGES` | `2` | Halaman discovery terbaru |
| `YT_SEARCH_REFRESH_HOURS` | `6` | Interval discovery ulang |
| `YT_MAX_VIDEOS_PER_TOPIC` | `150` | Batas video per topik |
| `YT_STATS_INTERVAL_MINUTES` | `60` | Interval snapshot statistik |
| `YT_COMMENTS_ENABLED` | `false` | Wajib false pada v3 |
| `YT_EXCLUDE_TERMS` | `upin ipin,...` | Istilah hiburan/noise yang dikeluarkan dari feed YouTube |
| `VIDEO_CLASSIFIER` | `auto` | Gemini bila tersedia, lalu fallback aturan |
| `GEMINI_API_KEY` | kosong | Klasifikasi judul dan fitur AI tahap lanjut |
| `GEMINI_API_KEYS` | kosong | Pool key Gemini server-side; diputar otomatis saat quota/rate-limit |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model Gemini; fallback leksikon tetap dipakai bila API sibuk/gagal |
| `MAPS_PROVIDER` | `apify` | Provider Maps POC (`apify` atau `places` untuk integrasi berikutnya) |
| `APIFY_TOKEN` | kosong | Token server Apify; jangan pernah dikirim ke browser |
| `APIFY_MAPS_TOKEN` | kosong | Token khusus Google Maps; fallback ke `APIFY_TOKEN` |
| `APIFY_SOCIAL_TOKEN` | kosong | Token khusus TikTok, Instagram, dan Facebook; fallback ke `APIFY_TOKEN` |
| `APIFY_MARKETPLACE_TOKEN` | kosong | Token khusus Shopee; fallback ke `APIFY_TOKEN` |
| `APIFY_ACTOR_ID` | `compass~crawler-google-places` | Actor Google Maps yang dijalankan |
| `APIFY_POLL_INTERVAL_SECONDS` | `5` | Jeda polling status run |
| `APIFY_POLL_TIMEOUT_SECONDS` | `600` | Batas waktu satu run |
| `MAPS_MAX_PLACES_PER_SEARCH` | `3` | Cap tempat per kota pada POC |
| `MAPS_MAX_REVIEWS_PER_PLACE` | `10` | Cap ulasan terbaru yang tersedia per tempat; tidak dibatasi hanya 7 hari terakhir |
| `GOOGLE_MAPS_API_KEY` | kosong | Disimpan untuk provider Places API langsung di tahap berikutnya |
| `MAPS_DAILY_REQUEST_CAP` | `30` | Hard cap request Maps per hari |
| `MAPS_MONTHLY_REQUEST_CAP` | `800` | Hard cap request Maps per bulan |
| `DEFAULT_CITY` | `Bandung` | Kota awal untuk topik baru |
| `TIKTOK_ACTOR_ID` | `clockworks~tiktok-scraper` | Actor TikTok |
| `INSTAGRAM_ACTOR_ID` | `apify~instagram-scraper` | Actor Instagram |
| `SOCIAL_RESULTS_PER_QUERY` | `50` | Post per keyword/hashtag |
| `SOCIAL_MAX_QUERIES_PER_TOPIC` | `3` | Keyword/hashtag per run |
| `SOCIAL_LOOKBACK_DAYS` | `30` | Window post yang disimpan |
| `SOCIAL_REFRESH_HOURS` | `12` | Interval refresh TikTok/Instagram/Facebook |
| `SOCIAL_DAILY_RUN_CAP` | `30` | Cap agregat run sosial per hari untuk indikator UI |
| `SOCIAL_MONTHLY_RUN_CAP` | `600` | Cap agregat run sosial per bulan untuk indikator UI |
| `SOCIAL_PLATFORM_DAILY_RUN_CAP` | `10` | Cap terpisah per platform per hari agar Facebook tidak kehabisan jatah |
| `SOCIAL_PLATFORM_MONTHLY_RUN_CAP` | `200` | Cap terpisah per platform per bulan |
| `MARKETPLACE_DAILY_RUN_CAP` | `20` | Cap run Shopee per hari |
| `MARKETPLACE_MONTHLY_RUN_CAP` | `400` | Cap run Shopee per bulan |
| `SOCIAL_SENTIMENT_ENABLED` | `true` | Analisis sentimen caption sosial yang relevan |
| `MAX_ACTIVE_TOPICS` | `20` | Batas topik aktif |
| `DATABASE_BACKEND` | `auto` | Memakai Postgres bila `SUPABASE_DB_URL` tersedia, selain itu SQLite |
| `SUPABASE_DB_URL` | kosong | Connection string Supabase server-side untuk data persisten |
| `DATABASE_AUTO_MIGRATE` | `false` | Bootstrap schema dari aplikasi; wajib false pada serverless production |
| `INTERNAL_REFRESH_TOKEN` | kosong | Token server-only untuk refresh operasional Facebook/Shopee; endpoint nonaktif bila kosong |
| `DATABASE_PATH` | `data/app.db` | SQLite lokal |

Saat `VIDEO_CLASSIFIER=auto` dan `GEMINI_API_KEY` atau `GEMINI_API_KEYS` tersedia, maksimal 50 judul diklasifikasikan per request menjadi `review`, `resep`, `ide_usaha`, atau `lainnya`. Judul diperlakukan sebagai data, request melewati rate limiter bersama, key diputar saat quota/rate-limit, dan kegagalan selalu jatuh ke aturan lokal.

## Setup key dan Apify

Untuk mode API resmi:

1. Buat project Google Cloud.
2. Aktifkan **YouTube Data API v3**.
3. Buat token Apify dengan scope minimum yang diperlukan. Isi token per layanan (`APIFY_MAPS_TOKEN`, `APIFY_SOCIAL_TOKEN`, `APIFY_MARKETPLACE_TOKEN`) atau gunakan satu `APIFY_TOKEN` sebagai fallback (server saja).
4. Biarkan `MAPS_PROVIDER=apify`; aplikasi memakai Actor `compass~crawler-google-places` dan cap lokal `MAPS_*`.
5. Jika kelak memakai provider Places langsung, baru isi `GOOGLE_MAPS_API_KEY` dan ubah `MAPS_PROVIDER=places`.
6. Jika memakai Maps Embed, buat key browser berbeda yang hanya mengizinkan Maps Embed API dan referrer aplikasi.
7. Buat Gemini key melalui Google AI Studio dan isi `GEMINI_API_KEY`.

Referensi Actor: [input schema Google Maps Scraper](https://apify.com/compass/crawler-google-places/input-schema) dan [API Actor](https://apify.com/compass/crawler-google-places/api).

Referensi sosial: [TikTok Scraper input](https://apify.com/clockworks/tiktok-scraper/input-schema), [TikTok API](https://apify.com/clockworks/tiktok-scraper/api), [Instagram Scraper input](https://apify.com/apify/instagram-scraper/input-schema), [Instagram API](https://apify.com/apify/instagram-scraper/api), dan [Facebook Search Scraper input](https://apify.com/apify/facebook-search-scraper/input-schema). Referensi marketplace: [Shopee Scraper input](https://apify.com/xtracto/shopee-scraper/input-schema) dan [Shopee Scraper API](https://apify.com/xtracto/shopee-scraper/api). Token hanya dipakai server; pemisahan per layanan membuat budget dan rotasi credential lebih aman.

Restart server setelah mengubah `.env`. Jangan pernah menggunakan key server di JavaScript browser.

## Metrik Panel A

- **Video baru 30 hari** dibanding 30 hari sebelumnya.
- **Indeks perhatian**: median views per hari dari video berumur maksimal 30 hari.
- **Kenaikan views 1/24 jam**: selisih snapshot nyata. Perbandingan 24 jam butuh riwayat 48 jam.
- **Coverage**: porsi video yang memiliki pasangan snapshot yang cukup.
- **Content mix**: proporsi review, resep, ide usaha, dan lainnya.
- **Persaingan ide usaha** meningkat hanya jika volume dan proporsinya benar-benar bertambah.

Snapshot tidak diubah setelah ditulis. Event `trend_tick` dikirim lewat Server-Sent Events sehingga browser memperbarui metrik tanpa reload.

## Endpoint v3

- `GET /api/health` — mode sumber, konfigurasi key, dan status AI.
- `GET /api/usage` — unit YouTube dan request Maps, sosial, serta marketplace terhadap cap.
- `GET /api/topics` — watchlist produk.
- `POST /api/topics/suggest` — saran kata kunci cepat.
- `POST /api/topics` — tambah topik dan mulai discovery latar belakang.
- `DELETE /api/topics/{id}` — nonaktifkan topik.
- `GET /api/trend?topic_id=...` — seluruh metrik tren.
- `GET /api/trend/videos?topic_id=...&sort=gain&type=review` — tabel bukti video.
- `GET /api/maps/places?topic_id=...` — tempat relevan dan snapshot rating dari koleksi Apify.
- `GET /api/maps/feed?topic_id=...` — opini Maps yang lolos filter produk.
- `GET /api/social/feed?topic_id=...&platform=tiktok|instagram|facebook` — post publik yang caption-nya relevan.
- `GET /api/social/stats?topic_id=...` — jumlah post, agregat engagement, distribusi sentiment, aspek, dan trend harian.
- `GET /api/marketplace/products?topic_id=...&platform=shopee` — produk Shopee yang lolos filter keyword.
- `GET /api/marketplace/stats?topic_id=...&platform=shopee` — agregat harga, rating, dan sold count.
- `GET /api/stream` — `trend_tick`, `topic_status`, dan keep-alive.
- `GET /docs` — dokumentasi OpenAPI interaktif.

Endpoint v2 masih ada sementara untuk kompatibilitas internal, tetapi dashboard P3 hanya memakai endpoint v3 di atas.

## Arsitektur

```text
Topik produk
   │
   ├── YouTube discovery ── filter relevansi ── klasifikasi jenis
   │                                             │
   │                                             ▼
   │                                      videos + snapshots
   │                                             │
   │                               metrik deterministik + SSE
   │                                             │
   └─────────────────────────────────────────────▼
                                         Dashboard Panel A

Google Maps usage guard ──► Apify Actor run ──► polling ──► dataset
                                      │
                                      └── filter relevansi ──► places + opini produk
```

Supabase Postgres menjadi storage persisten saat `SUPABASE_DB_URL` tersedia; SQLite tetap dipakai untuk development dan test. Keduanya memakai index per topik/waktu dan tabel `api_usage` persisten. Pencarian YouTube yang mahal dan pembacaan statistik yang murah memiliki bucket kuota terpisah. Hari YouTube mengikuti zona waktu Pasifik; cap Maps mengikuti UTC.

## Testing

```bash
source .venv/bin/activate
python -m pytest -q
node --check static/app.js
node --check static/ui.js
```

Seluruh test memakai SQLite sementara, fake client, atau `httpx.MockTransport`; test tidak memanggil YouTube, Google Maps, atau Gemini sungguhan.

## Reset data

```bash
python scripts/reset_db.py
```

Perintah ini menghapus database lokal aplikasi, membuat schema v3, dan menanam tiga topik awal. Gunakan hanya saat data lokal memang boleh diganti.

## Privasi dan kepatuhan

- Key server tidak pernah masuk response API atau frontend.
- Panel tren menyimpan metadata publik dan snapshot agregat video, bukan komentar YouTube.
- Implementasi Maps menjaga atribusi penulis/Google, TTL konten, pembatasan cache, dan ketentuan sumber yang dipakai. Place ID dapat dipertahankan; konten Places/ulasan memiliki TTL POC.
- Data Places tidak boleh ditempelkan pada peta non-Google.
- Tinjau ketentuan Google Maps Platform terbaru sebelum penggunaan produksi; TTL POC bukan jaminan kepatuhan.

## Struktur penting

```text
app/youtube/       discovery, client, quota, snapshot, metrik, scheduler
app/maps/          Apify client, parser, relevansi, collector, error, budget guard
app/social/        TikTok, Instagram, Facebook, sentiment, collector, budget guard
app/marketplace/   Shopee Apify client, parser, collector, budget guard
app/topics/        layanan watchlist produk
app/api/           endpoint topics, trend, usage, health, SSE
static/            dashboard P3 responsif
config/            seed topik dan katalog kompatibilitas
scripts/           reset database dan probe sumber
tests/             unit/integrasi tanpa API eksternal
```

Spesifikasi implementasi lengkap ada di [SPEC.md](SPEC.md).
