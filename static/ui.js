import { state } from "./state.js";

const $ = (id) => document.getElementById(id);
const number = new Intl.NumberFormat("id-ID", { notation: "compact", maximumFractionDigits: 1 });
const fullNumber = new Intl.NumberFormat("id-ID");
const date = new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short", year: "numeric" });

function escapeHtml(value = "") { return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[character])); }
function relativeTime(value) {
  if (!value) return "Belum ada snapshot";
  const minute = Math.floor(Math.max(0, Date.now() - new Date(value).getTime()) / 60000);
  if (minute < 1) return "Baru saja";
  if (minute < 60) return `${minute} menit lalu`;
  const hour = Math.floor(minute / 60); return hour < 24 ? `${hour} jam lalu` : `${Math.floor(hour / 24)} hari lalu`;
}
function trendBadge(id, trend, change) {
  const element = $(id); const map = { naik: ["naik", "↗ Naik"], turun: ["turun", "↘ Turun"], stabil: ["neutral", "→ Stabil"], butuh_data: ["neutral", "Butuh data"] };
  const [className, label] = map[trend] || map.butuh_data; element.className = `trend-badge ${className}`;
  element.textContent = change === null || change === undefined ? label : `${change > 0 ? "+" : ""}${Math.round(change)}%`;
}

export function setConnection(connected) {
  const element = $("connection-status"); element.classList.toggle("is-live", connected); element.classList.toggle("is-connecting", !connected);
  element.querySelector(".connection-label").textContent = connected ? "LIVE" : "Menyambung…";
}
export function renderHealth() {
  const health = state.health || {}; const mapsActive = Boolean(health.maps_configured);
  $("maps-status-badge").className = `source-chip ${mapsActive ? "is-on" : "is-off"}`; $("maps-status-badge").textContent = mapsActive ? `${health.maps_provider === "apify" ? "Apify aktif" : "Places aktif"}` : "Belum dikonfigurasi";
  $("maps-status-copy").textContent = mapsActive ? "Server menjalankan pencarian tempat dan ulasan terbaru melalui Apify." : "Google Maps belum dikonfigurasi di server; data tersimpan tetap aman dan tidak dihapus.";
  renderSourceNavigation();
}

const sourceNames = { overview: "Ringkasan", tiktok: "TikTok", instagram: "Instagram", facebook: "Facebook", maps: "Google Maps", youtube: "YouTube", shopee: "Shopee" };
function sourceState(key) { return state.sourceStates?.[key] || { loading: false, loaded: false, error: "" }; }
function socialPostsForSource(source = state.activeSource) {
  const posts = state.socialPosts || [];
  return source === "tiktok" || source === "instagram" || source === "facebook" ? posts.filter((post) => post.platform === source) : posts;
}
export function renderSourceNavigation() {
  const counts = { tiktok: socialPostsForSource("tiktok").length, instagram: socialPostsForSource("instagram").length, facebook: socialPostsForSource("facebook").length, maps: (state.mapsPlaces || []).filter((place) => place.is_relevant).length + (state.mapsFeed || []).length, youtube: (state.videos || []).length, shopee: (state.marketplaceProducts || []).length };
  ["tiktok", "instagram", "facebook", "maps", "youtube", "shopee"].forEach((key) => {
    const button = document.querySelector(`#source-nav [data-source="${key}"]`); const dot = $(`source-status-${key}`); const count = $(`source-count-${key}`); const status = ["tiktok", "instagram", "facebook"].includes(key) ? sourceState("social") : key === "shopee" ? sourceState("marketplace") : sourceState(key);
    button?.classList.toggle("active", state.activeSource === key); button?.toggleAttribute("aria-current", state.activeSource === key); if (count) count.textContent = status.loading && !status.loaded ? "…" : String(counts[key]);
    if (dot) { dot.className = `source-status-dot ${status.loading ? "is-loading" : status.error ? "is-error" : status.loaded ? "is-live" : ""}`; dot.title = status.error || (status.loading ? "Refresh background berjalan" : status.loaded ? "Data tersedia" : "Menunggu data"); }
  });
  const overview = $("source-status-overview"); if (overview) overview.className = `source-status-dot ${["youtube", "maps", "social", "marketplace"].some((key) => sourceState(key).loading) ? "is-loading" : "is-live"}`;
  const socialState = sourceState("social"); const mapsState = sourceState("maps"); const youtubeState = sourceState("youtube"); const marketplaceState = sourceState("marketplace");
  const setSummary = (key, value, note) => { const valueEl = $(`overview-${key}-count`); const noteEl = $(`overview-${key}-note`); if (valueEl) valueEl.textContent = value; if (noteEl) noteEl.textContent = note; };
  setSummary("tiktok", socialState.loading && !socialState.loaded ? "…" : String(counts.tiktok), socialState.loading ? "Mengambil post" : counts.tiktok ? "post relevan" : "Belum ada post");
  setSummary("instagram", socialState.loading && !socialState.loaded ? "…" : String(counts.instagram), socialState.loading ? "Mengambil caption" : counts.instagram ? "post relevan" : "Belum ada post");
  setSummary("maps", mapsState.loading && !mapsState.loaded ? "…" : String(counts.maps), mapsState.loading ? "Mencari lokasi" : counts.maps ? "lokasi & ulasan" : "Belum ada ulasan");
  setSummary("youtube", youtubeState.loading && !youtubeState.loaded ? "…" : String(counts.youtube), youtubeState.loading ? "Mencari video" : counts.youtube ? "video relevan" : "Belum ada video");
  setSummary("facebook", socialState.loading && !socialState.loaded ? "…" : String(counts.facebook), socialState.loading ? "Mengambil post" : counts.facebook ? "post relevan" : "Belum ada post");
  setSummary("shopee", marketplaceState.loading && !marketplaceState.loaded ? "…" : String(counts.shopee), marketplaceState.loading ? "Mencari produk" : counts.shopee ? "produk relevan" : "Belum ada produk");
}
export function renderActiveSource() {
  const source = state.activeSource; const view = source === "tiktok" || source === "instagram" || source === "facebook" ? "social" : source;
  document.querySelectorAll("[data-source-view]").forEach((element) => element.classList.toggle("is-active", element.dataset.sourceView === view));
  document.querySelectorAll("#source-nav [data-source]").forEach((button) => { const active = button.dataset.source === source; button.classList.toggle("active", active); if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current"); });
  const name = sourceNames[source] || sourceNames.overview; $("source-breadcrumb").textContent = `${name} · ${state.topics.find((topic) => topic.id === state.activeTopicId)?.name || "pilih produk"}`;
  $("hero-source-badge").textContent = name; $("social-source-label").textContent = source === "tiktok" ? "Sentimen pasar · TikTok" : source === "instagram" ? "Sentimen pasar · Instagram" : source === "facebook" ? "Sentimen pasar · Facebook" : "Sentimen pasar · TikTok, Instagram & Facebook";
  $("social-panel-title").textContent = source === "tiktok" ? "Video TikTok yang sedang ramai" : source === "instagram" ? "Caption Instagram yang sedang ramai" : source === "facebook" ? "Post Facebook yang sedang ramai" : "Suara pasar yang sedang ramai";
}
export function renderSourceProgress() {
  const active = ["tiktok", "instagram", "facebook"].includes(state.activeSource) ? "social" : state.activeSource === "shopee" ? "marketplace" : state.activeSource; const group = active === "overview" ? ["youtube", "maps", "social", "marketplace"] : [active]; const statuses = group.map(sourceState); const loading = statuses.some((status) => status.loading); const loaded = statuses.length > 0 && statuses.every((status) => status.loaded); const errors = statuses.find((status) => status.error);
  const topic = state.topics.find((item) => item.id === state.activeTopicId); const title = $("source-progress-title"); const copy = $("source-progress-copy"); const bar = $("source-progress-bar"); const percent = $("source-progress-percent"); const card = $("source-progress");
  if (loaded && !loading) { card.classList.add("is-loaded"); title.textContent = "Data tersimpan sudah tampil"; copy.textContent = "Refresh sumber tetap berjalan otomatis di background; dashboard tidak dikosongkan saat proses berlangsung."; bar.style.width = "100%"; percent.textContent = "Siap"; }
  else if (errors) { card.classList.remove("is-loaded"); title.textContent = "Sebagian sumber perlu dicoba lagi"; copy.textContent = `${errors.error}. Data dari sumber lain tetap bisa dibaca.`; bar.style.width = `${Math.max(18, Math.round((statuses.filter((status) => status.loaded).length / statuses.length) * 100))}%`; percent.textContent = "Perlu cek"; }
  else if (loading || topic?.status === "discovering") { card.classList.remove("is-loaded"); const label = active === "overview" ? "sumber data" : active === "social" ? sourceNames[state.activeSource] || "TikTok, Instagram & Facebook" : active === "marketplace" ? "Shopee" : sourceNames[active]; title.textContent = `Memuat ${label}`; copy.textContent = "Membaca snapshot Supabase lebih dulu, lalu pengambilan baru berjalan hemat token di background."; const done = statuses.filter((status) => status.loaded).length; bar.style.width = `${Math.max(22, Math.round((done / statuses.length) * 100))}%`; percent.textContent = `${Math.max(22, Math.round((done / statuses.length) * 100))}%`; }
  else { card.classList.remove("is-loaded"); title.textContent = "Menyiapkan sumber data"; copy.textContent = "Pilih sumber di sidebar. Data yang sudah tersimpan tidak akan hilang saat refresh."; bar.style.width = "10%"; percent.textContent = "10%"; }
}
export function renderUsage() {
  const element = $("apify-usage"); if (!element) return;
  const health = state.health || {}; const social = state.usage?.social;
  if (!health.apify_configured) {
    element.className = "apify-usage is-off"; element.innerHTML = "<strong>Apify belum aktif</strong><span>Token server belum siap</span>"; return;
  }
  if (!social) {
    const maps = state.usage?.maps || {}; const marketplace = state.usage?.marketplace || {}; element.className = "apify-usage";
    element.innerHTML = `<strong>Apify token aktif</strong><span>Maps ${Number(maps.today || 0)}/${Number(maps.daily_limit || 0)} · Shopee ${Number(marketplace.today || 0)}/${Number(marketplace.daily_limit || 0)} run</span>`; return;
  }
  const daily = Number(social.today || 0); const dailyLimit = Number(social.daily_limit || 0); const monthly = Number(social.this_month || 0); const monthlyLimit = Number(social.monthly_limit || 0);
  const ratio = dailyLimit ? daily / dailyLimit : 0; element.className = `apify-usage ${ratio >= .85 ? "is-warning" : ""}`;
  const marketplace = state.usage?.marketplace || {}; element.innerHTML = `<strong>Apify ${daily}/${dailyLimit} run hari ini</strong><span>${monthly}/${monthlyLimit} sosial · Shopee ${Number(marketplace.today || 0)}/${Number(marketplace.daily_limit || 0)} · ${health.social_sentiment_enabled ? "sentiment aktif" : "sentiment off"}</span>`;
}
export function renderTopics() {
  $("topic-tabs").innerHTML = state.topics.length ? state.topics.map((topic) => {
    const selected = topic.id === state.activeTopicId; const count = Number(topic.videos_tracked || 0);
    return `<button type="button" role="tab" aria-selected="${selected}" class="topic-tab ${selected ? "active" : ""}" data-topic-id="${escapeHtml(topic.id)}"><span>${escapeHtml(topic.name)}</span><small>${count ? `${count} video` : topic.status === "discovering" ? "mencari…" : "belum ada"}</small></button>`;
  }).join("") : '<p class="watchlist-empty">Belum ada produk. Tambahkan produk pertama untuk mulai mencari tren.</p>';
  const cap = Number(state.health?.max_active_topics || 20); $("topic-cap-note").textContent = `${state.topics.length}/${cap} aktif`;
  const topic = state.topics.find((item) => item.id === state.activeTopicId);
  $("topic-title").textContent = topic ? `Apa yang terjadi pada “${topic.name}”?` : "Pilih produk untuk melihat tren";
  $("topic-subtitle").textContent = topic ? `Sentimen sosial, opini lokasi, dan tren video untuk produk terkait · target ${topic.cities.join(", ")}` : "Tambahkan produk UMKM untuk memulai pemantauan sumber data secara live.";
  if ($("overview-topic-status")) $("overview-topic-status").textContent = topic?.status === "discovering" ? "Pengumpulan berjalan" : topic ? "Produk aktif" : "Menyiapkan…";
  renderActiveSource(); renderSourceProgress();
  if (topic?.status === "discovering") showBanner("discovering", `Penelusuran YouTube untuk “${topic.name}” sedang berjalan.`);
  else if (topic?.status === "limited" && !topic.videos_tracked) showBanner("limited", "Belum menemukan video yang cukup relevan. Coba kata produk yang lebih spesifik.");
  else $("topic-banner").hidden = true;
}
export function showBanner(status, message) {
  const banner = $("topic-banner"); banner.className = `topic-banner ${status === "limited" ? "is-warning" : "is-loading"}`;
  banner.innerHTML = `<span class="banner-spinner"></span>${escapeHtml(message)}`; banner.hidden = false;
}
function chart(id, configuration) {
  if (!window.Chart) return null;
  state.charts[id]?.destroy(); const context = $(id).getContext("2d"); state.charts[id] = new window.Chart(context, configuration); return state.charts[id];
}
const chartDefaults = {
  responsive: true, maintainAspectRatio: false, animation: false, interaction: { intersect: false, mode: "index" },
  plugins: { legend: { display: false }, tooltip: { backgroundColor: "#101a17", padding: 12, cornerRadius: 8, titleColor: "#83e6a7", bodyColor: "#f5f2e9" } },
  scales: { x: { grid: { display: false }, ticks: { color: "#7b8580", maxRotation: 0, autoSkip: true, maxTicksLimit: 7, font: { size: 10 } }, border: { display: false } }, y: { beginAtZero: true, grid: { color: "rgba(117,128,122,.14)" }, ticks: { color: "#7b8580", precision: 0, font: { size: 10 } }, border: { display: false } } },
};
function renderWeekly(items) {
  const hasData = items.some((item) => item.count > 0); $("weekly-empty").hidden = hasData; $("weekly-chart").hidden = !hasData;
  if (!hasData) { state.charts["weekly-chart"]?.destroy(); return; }
  chart("weekly-chart", { type: "bar", data: { labels: items.map((item) => new Date(`${item.week_start}T00:00:00`).toLocaleDateString("id-ID", { day: "numeric", month: "short" })), datasets: [{ data: items.map((item) => item.count), backgroundColor: "#83e6a7", hoverBackgroundColor: "#4bcf7e", borderRadius: 7, borderSkipped: false, maxBarThickness: 34 }] }, options: chartDefaults });
}
function renderHourly(items) {
  const hasData = items.length > 0 && items.some((item) => item.gain > 0); $("hourly-empty").hidden = hasData; $("hourly-chart").hidden = !hasData;
  if (!hasData) { state.charts["hourly-chart"]?.destroy(); return; }
  const context = $("hourly-chart").getContext("2d"); const gradient = context.createLinearGradient(0, 0, 0, 250); gradient.addColorStop(0, "rgba(131,230,167,.35)"); gradient.addColorStop(1, "rgba(131,230,167,0)");
  chart("hourly-chart", { type: "line", data: { labels: items.map((item) => new Date(item.captured_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })), datasets: [{ data: items.map((item) => item.gain), borderColor: "#42c879", backgroundColor: gradient, fill: true, tension: .35, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2.5 }] }, options: chartDefaults });
}
function renderMix(mix) {
  const labels = { review: "Review produk", resep: "Resep / cara pakai", ide_usaha: "Ide usaha", lainnya: "Lainnya" }; const colors = { review: "#83e6a7", resep: "#101a17", ide_usaha: "#f0b85d", lainnya: "#d8ddd9" };
  const entries = Object.entries(mix || {}); const total = entries.reduce((sum, [, value]) => sum + value.count, 0); $("mix-total").textContent = fullNumber.format(total);
  $("content-legend").innerHTML = entries.map(([key, value]) => `<li><i style="background:${colors[key]}"></i><span>${labels[key]}</span><strong>${Math.round(value.share * 100)}%</strong></li>`).join("");
  if (!entries.length || !total) { state.charts["content-chart"]?.destroy(); return; }
  chart("content-chart", { type: "doughnut", data: { labels: entries.map(([key]) => labels[key]), datasets: [{ data: entries.map(([, value]) => value.count), backgroundColor: entries.map(([key]) => colors[key]), borderWidth: 0, hoverOffset: 3 }] }, options: { responsive: true, maintainAspectRatio: false, animation: false, cutout: "72%", plugins: { legend: { display: false }, tooltip: chartDefaults.plugins.tooltip } } });
}
export function renderMetrics() {
  const metrics = state.metrics;
  if (!metrics) { ["kpi-new-videos", "kpi-attention", "kpi-gain", "kpi-competition"].forEach((id) => { $(id).textContent = "—"; }); $("last-update").textContent = "Belum ada snapshot"; renderWeekly([]); renderHourly([]); renderMix({}); return; }
  $("kpi-new-videos").textContent = fullNumber.format(metrics.new_videos_30d); $("kpi-new-note").textContent = `${fullNumber.format(metrics.new_videos_prev_30d)} video pada 30 hari sebelumnya`;
  $("kpi-attention").textContent = metrics.attention_index === null ? "—" : `${number.format(metrics.attention_index)} / hari`; $("kpi-gain").textContent = metrics.views_gain_24h === null ? "—" : `+${number.format(metrics.views_gain_24h)}`;
  $("kpi-gain-note").textContent = metrics.attention_change_pct === null ? "Butuh 48 jam data untuk pembanding" : `${metrics.attention_change_pct > 0 ? "+" : ""}${Math.round(metrics.attention_change_pct)}% vs 24 jam sebelumnya`;
  $("coverage-badge").textContent = `${Math.round(metrics.coverage * 100)}% cakupan`; $("kpi-competition").textContent = metrics.competition_signal === "meningkat" ? "Meningkat" : "Stabil";
  $("kpi-competition-note").textContent = metrics.competition_signal === "meningkat" ? "Proporsi video ide usaha bertambah" : "Belum ada lonjakan konten ide usaha"; $("last-update").textContent = `Snapshot ${relativeTime(metrics.last_snapshot_at)}`;
  $("live-ticker").textContent = `+${fullNumber.format(metrics.views_gain_since_last || 0)} sejak snapshot`; trendBadge("supply-trend", metrics.supply_trend, metrics.supply_change_pct); trendBadge("attention-trend", metrics.attention_trend, metrics.attention_change_pct);
  renderWeekly(metrics.weekly_new_videos || []); renderHourly(metrics.hourly_gain_series || []); renderMix(metrics.content_mix || {});
}
export function renderVideos() {
  const labels = { review: "Review", resep: "Resep", ide_usaha: "Ide usaha", lainnya: "Lainnya" }; const items = state.videos || [];
  $("video-table-body").innerHTML = items.map((video) => `<tr><td><a class="video-title" href="${escapeHtml(video.url)}" target="_blank" rel="noopener"><span>${escapeHtml(video.title)}</span><small>${escapeHtml(video.channel_title)}</small></a></td><td><span class="type-chip type-${escapeHtml(video.content_type)}">${labels[video.content_type]}</span></td><td>${date.format(new Date(video.published_at))}</td><td class="numeric">${fullNumber.format(video.views)}</td><td class="numeric">${number.format(video.views_per_day)}</td><td class="numeric gain">${video.gain_24h === null ? "—" : `+${number.format(video.gain_24h)}`}</td></tr>`).join("");
  $("video-empty").hidden = items.length > 0; $("video-table-note").textContent = `${items.length} video ditampilkan · komentar YouTube tidak digunakan`;
  $("trend-source-note").textContent = `Data tren dari YouTube · berdasarkan sampel ${state.metrics?.videos_tracked || 0} video`;
}
export function renderMaps() {
  const places = state.mapsPlaces || []; const feed = state.mapsFeed || [];
  const relevantPlaces = places.filter((place) => place.is_relevant);
  $("maps-count-badge").textContent = `${relevantPlaces.length} tempat`;
  $("maps-empty").hidden = relevantPlaces.length > 0 || feed.length > 0;
  $("maps-places-body").innerHTML = relevantPlaces.map((place) => `<tr><td><a class="maps-place-link" href="${escapeHtml(place.maps_uri || "#")}" target="_blank" rel="noopener">${escapeHtml(place.name || "Tempat")}</a><small class="maps-place-address">${escapeHtml(place.address || "")}</small></td><td>${escapeHtml(place.city || "—")}</td><td class="numeric">${place.rating == null ? "—" : Number(place.rating).toFixed(1)}</td><td class="numeric">${place.user_rating_count == null ? "—" : fullNumber.format(place.user_rating_count)}</td></tr>`).join("");
  const placeNames = Object.fromEntries(places.map((place) => [place.place_id, place.name]));
  $("maps-feed-list").innerHTML = feed.map((item) => `<article class="maps-feed-item"><div class="maps-feed-meta"><span class="maps-feed-stars">${item.stars == null ? "☆" : `${"★".repeat(Math.max(0, Math.min(5, Number(item.stars))))}${"☆".repeat(Math.max(0, 5 - Number(item.stars)))}`}</span><time>${item.created_at ? date.format(new Date(item.created_at)) : "Baru"}</time></div><p class="maps-feed-text">${escapeHtml(item.text)}</p><p class="maps-feed-place">${escapeHtml(placeNames[item.place_id] || "Google Maps")}</p></article>`).join("");
  $("maps-source-note").textContent = `Sumber: Google Maps melalui Apify · ${feed.length} opini produk tersaring · ulasan tempat tidak dicampurkan`;
  const mapState = sourceState("maps"); if (!(relevantPlaces.length || feed.length)) { const copy = $("maps-empty")?.querySelector("span"); if (copy) copy.textContent = mapState.loading ? "Data tersimpan sedang dibaca; pengambilan baru berjalan di background." : mapState.error ? "Sumber Maps gagal dimuat. Coba refresh setelah konfigurasi diperiksa." : "Belum ada ulasan relevan untuk produk ini."; }
}
function renderSocialTrend(daily) {
  const items = (daily || []).filter((item) => item.date && (item.positif || item.negatif || item.netral));
  const empty = $("social-trend-empty"); const canvas = $("social-sentiment-chart"); const hasData = items.length > 0;
  empty.hidden = hasData; canvas.hidden = !hasData;
  if (!hasData) { state.charts["social-sentiment-chart"]?.destroy(); return; }
  chart("social-sentiment-chart", { type: "line", data: { labels: items.map((item) => new Date(`${item.date}T00:00:00`).toLocaleDateString("id-ID", { day: "numeric", month: "short" })), datasets: [
    { label: "Positif", data: items.map((item) => item.positif || 0), borderColor: "#42c879", backgroundColor: "rgba(66,200,121,.12)", fill: true, tension: .35, pointRadius: 2, borderWidth: 2 },
    { label: "Negatif", data: items.map((item) => item.negatif || 0), borderColor: "#bd5343", backgroundColor: "rgba(189,83,67,.08)", fill: true, tension: .35, pointRadius: 2, borderWidth: 2 },
    { label: "Netral", data: items.map((item) => item.netral || 0), borderColor: "#8b9690", backgroundColor: "transparent", fill: false, tension: .35, pointRadius: 2, borderWidth: 1.5 },
  ] }, options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } }, scales: { ...chartDefaults.scales, x: { ...chartDefaults.scales.x, maxTicksLimit: 5 }, y: { ...chartDefaults.scales.y, ticks: { ...chartDefaults.scales.y.ticks, precision: 0 } } } } });
}
export function renderSocial() {
  const posts = socialPostsForSource();
  const baseStats = state.socialStats || {}; const sourceSpecific = ["tiktok", "instagram", "facebook"].includes(state.activeSource);
  const sentiment = baseStats.sentiment || {}; const positive = sourceSpecific ? posts.filter((post) => post.sentiment === "positif").length : Number(sentiment.positif || 0); const negative = sourceSpecific ? posts.filter((post) => post.sentiment === "negatif").length : Number(sentiment.negatif || 0); const neutral = sourceSpecific ? posts.filter((post) => post.sentiment === "netral").length : Number(sentiment.netral || 0); const pending = sourceSpecific ? posts.filter((post) => !post.sentiment || post.sentiment === "pending").length : Number(sentiment.pending || 0); const analyzed = positive + negative + neutral || Number(baseStats.analyzed_posts || 0);
  const sourceDaily = Object.values(posts.reduce((days, post) => { const key = post.published_at ? new Date(post.published_at).toISOString().slice(0, 10) : ""; if (!key) return days; const day = days[key] || { date: key, positif: 0, negatif: 0, netral: 0 }; if (post.sentiment === "positif" || post.sentiment === "negatif" || post.sentiment === "netral") day[post.sentiment] += 1; days[key] = day; return days; }, {}));
  const stats = sourceSpecific ? { ...baseStats, analyzed_posts: analyzed, positive_rate: analyzed ? positive / analyzed : 0, negative_rate: analyzed ? negative / analyzed : 0, dominant_sentiment: analyzed ? (positive >= negative && positive >= neutral ? "positif" : negative >= neutral ? "negatif" : "netral") : (pending ? "pending" : null), daily: sourceDaily } : baseStats;
  $("social-count-badge").textContent = `${posts.length} post`;
  $("social-positive-count").textContent = fullNumber.format(positive); $("social-negative-count").textContent = fullNumber.format(negative); $("social-neutral-count").textContent = fullNumber.format(neutral + pending);
  $("social-positive-rate").textContent = `${Math.round(Number(stats.positive_rate || 0) * 100)}% dari dianalisis`; $("social-negative-rate").textContent = `${Math.round(Number(stats.negative_rate || 0) * 100)}% dari dianalisis`;
  const dominant = { positif: "Dominan positif", negatif: "Dominan negatif", netral: "Dominan netral", pending: "Menunggu analisis" }[stats.dominant_sentiment] || (pending ? "Menunggu analisis" : "Belum ada data"); $("social-dominant-sentiment").textContent = dominant;
  $("social-analyzer-note").textContent = state.health?.social_sentiment_enabled ? `Analyzer: ${state.health.social_sentiment_analyzer || "auto"} · ${analyzed} dianalisis` : "Sentiment dimatikan";
  const topics = stats.top_topics || []; $("social-topic-trend-list").innerHTML = topics.length ? topics.slice(0, 4).map((item) => `<li><span>${escapeHtml(item.topic)}</span><strong>${fullNumber.format(item.total)} sebutan</strong><small>+${item.positif || 0} positif · −${item.negatif || 0} negatif</small></li>`).join("") : "<li><span>Belum ada aspek</span><strong>—</strong><small>Hasil muncul setelah caption dianalisis.</small></li>";
  renderSocialTrend(stats.daily || []);
  $("social-empty").hidden = posts.length > 0;
  $("social-feed-list").innerHTML = posts.map((post) => {
    const platform = post.platform === "tiktok" ? "TikTok" : post.platform === "instagram" ? "Instagram" : "Facebook";
    const metrics = [post.views == null ? null : `▶ ${number.format(post.views)}`, post.likes == null ? null : `♥ ${number.format(post.likes)}`, post.comments == null ? null : `◌ ${number.format(post.comments)}`].filter(Boolean).join(" · ");
    const sentimentLabel = { positif: "Positif", negatif: "Negatif", netral: "Netral", pending: "Belum dianalisis" }[post.sentiment || "pending"] || "Belum dianalisis";
    return `<article class="social-feed-item"><div class="social-feed-meta"><span class="social-platform">${platform}</span><time>${post.published_at ? date.format(new Date(post.published_at)) : "Baru"}</time></div><p class="social-feed-author">${escapeHtml(post.author_name || "Akun publik")}</p><p class="social-feed-text">${escapeHtml(post.text)}</p><span class="social-sentiment-badge ${escapeHtml(post.sentiment || "pending")}">${sentimentLabel}</span><p class="social-feed-metrics">${escapeHtml(metrics || "Tanpa metrik")}</p>${post.url ? `<a class="social-feed-link" href="${escapeHtml(post.url)}" target="_blank" rel="noopener">Buka post ↗</a>` : ""}</article>`;
  }).join("");
  const socialState = sourceState("social"); const emptyCopy = $("social-empty")?.querySelector("span"); if (!posts.length && emptyCopy) emptyCopy.textContent = socialState.loading ? "Data tersimpan sedang dibaca; pengambilan baru berjalan di background." : socialState.error ? "Feed sosial gagal dimuat. Coba refresh setelah konfigurasi diperiksa." : "Belum ada post relevan untuk sumber ini.";
  const sourceLabel = state.activeSource === "tiktok" ? "TikTok" : state.activeSource === "instagram" ? "Instagram" : state.activeSource === "facebook" ? "Facebook" : "TikTok, Instagram & Facebook";
  $("social-source-note").textContent = `Sumber: ${sourceLabel} melalui Apify · ${posts.length} post relevan · sentiment dihitung dalam konteks Bahasa Indonesia`;
}
export function renderMarketplace() {
  const products = state.marketplaceProducts || []; const stats = state.marketplaceStats || {};
  $("marketplace-count-badge").textContent = `${products.length} produk`;
  $("marketplace-product-body").innerHTML = products.map((product) => `<tr><td><a class="marketplace-product-title" href="${escapeHtml(product.url || "#")}" target="_blank" rel="noopener"><span>${escapeHtml(product.title)}</span><small>${escapeHtml(product.shop_name || "Penjual Shopee")}</small></a></td><td>${product.price == null ? "—" : `Rp ${fullNumber.format(Math.round(Number(product.price)))}`}</td><td class="numeric">${product.rating == null ? "—" : Number(product.rating).toFixed(1)}</td><td class="numeric">${product.sold_count == null ? "—" : fullNumber.format(product.sold_count)}</td><td class="numeric">${product.rating_count == null ? "—" : fullNumber.format(product.rating_count)}</td></tr>`).join("");
  $("marketplace-empty").hidden = products.length > 0;
  $("marketplace-total-products").textContent = fullNumber.format(Number(stats.products || 0)); $("marketplace-total-sold").textContent = fullNumber.format(Number(stats.sold_count || 0)); $("marketplace-average-rating").textContent = stats.average_rating == null ? "—" : Number(stats.average_rating).toFixed(1); $("marketplace-price-range").textContent = stats.min_price == null ? "—" : `Rp ${fullNumber.format(Math.round(stats.min_price))}–${fullNumber.format(Math.round(stats.max_price || stats.min_price))}`;
  const marketplaceState = sourceState("marketplace"); const copy = $("marketplace-empty")?.querySelector("span"); if (!products.length && copy) copy.textContent = marketplaceState.loading ? "Snapshot Shopee sedang dibaca; pencarian baru berjalan di background." : marketplaceState.error ? "Feed Shopee gagal dimuat. Periksa Actor atau kuota Apify." : "Belum ada produk Shopee yang cocok dengan kata kunci produk.";
  $("marketplace-source-note").textContent = `Sumber: Shopee melalui Apify · ${products.length} produk relevan · max ${state.health?.marketplace_results_per_query || "30"} hasil per run`;
}
let toastTimer;
export function showToast(message) { const toast = $("toast"); toast.textContent = message; toast.classList.add("visible"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("visible"), 4200); }
