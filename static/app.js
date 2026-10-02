import { api } from "./api.js";
import { state } from "./state.js";
import { renderHealth, renderMarketplace, renderMaps, renderMetrics, renderSocial, renderTopics, renderUsage, renderVideos, renderSourceNavigation, renderActiveSource, renderSourceProgress, setConnection, showBanner, showToast } from "./ui.js";

const $ = (id) => document.getElementById(id);
let stream;
let topicRefreshTimer;
const sourceRequestIds = { youtube: 0, maps: 0, social: 0, marketplace: 0 };
const sourceLabels = { youtube: "YouTube", maps: "Google Maps", social: "TikTok, Instagram & Facebook", marketplace: "Shopee" };
const sourceRenderers = {
  youtube: () => { renderMetrics(); renderVideos(); },
  maps: renderMaps,
  social: renderSocial,
  marketplace: renderMarketplace,
};

async function refreshUsage() {
  try { state.usage = await api.usage(); renderUsage(); } catch { /* live usage is supplementary to the dashboard */ }
}

async function loadTopics(preferredId = "") {
  const payload = await api.topics(); state.topics = payload.items || [];
  const available = state.topics.some((item) => item.id === state.activeTopicId);
  state.activeTopicId = preferredId || (available ? state.activeTopicId : state.topics[0]?.id || "");
  renderTopics(); renderSourceNavigation(); return state.activeTopicId;
}
function newSourceStates(loading = false) {
  return Object.fromEntries(Object.keys(sourceRequestIds).map((key) => [key, { loading, loaded: false, error: "" }]));
}
function clearTopicData() {
  state.metrics = null; state.videos = []; state.mapsPlaces = []; state.mapsFeed = [];
  state.socialPosts = []; state.socialStats = null; state.marketplaceProducts = []; state.marketplaceStats = null;
}
function renderAllData() {
  renderMetrics(); renderVideos(); renderMaps(); renderSocial(); renderMarketplace(); renderSourceNavigation(); renderSourceProgress();
}
async function loadSource(key, work, apply) {
  const topicId = state.activeTopicId;
  if (!topicId) return;
  const requestId = ++sourceRequestIds[key];
  const previous = state.sourceStates[key] || {};
  state.sourceStates[key] = { loading: true, loaded: Boolean(previous.loaded), error: "" };
  renderSourceNavigation(); renderSourceProgress();
  const stillCurrent = () => requestId === sourceRequestIds[key] && topicId === state.activeTopicId;
  try {
    const result = await work(topicId);
    if (!stillCurrent()) return;
    apply(result); state.sourceStates[key] = { loading: false, loaded: true, error: "" };
    sourceRenderers[key](); renderSourceNavigation(); renderSourceProgress();
  } catch (error) {
    if (!stillCurrent()) return;
    state.sourceStates[key] = { loading: false, loaded: Boolean(previous.loaded), error: error.message };
    renderSourceNavigation(); renderSourceProgress();
    showToast(`${sourceLabels[key]} belum dapat dimuat: ${error.message}`);
  }
}
function loadYouTube() {
  return loadSource("youtube", (topicId) => Promise.all([api.trend(topicId), api.videos(topicId, state.videoSort, state.videoType)]), ([metrics, videoPayload]) => { state.metrics = metrics; state.videos = videoPayload.items || []; });
}
function loadVideos() {
  return loadSource("youtube", (topicId) => api.videos(topicId, state.videoSort, state.videoType), (payload) => { state.videos = payload.items || []; });
}
function loadMaps() {
  return loadSource("maps", (topicId) => Promise.all([api.mapsPlaces(topicId), api.mapsFeed(topicId)]), ([placesPayload, feedPayload]) => { state.mapsPlaces = placesPayload.items || []; state.mapsFeed = feedPayload.items || []; });
}
function loadSocial() {
  return loadSource("social", (topicId) => Promise.all([api.socialFeed(topicId), api.socialStats(topicId)]), ([socialPayload, stats]) => { state.socialPosts = socialPayload.items || []; state.socialStats = stats; });
}
function loadMarketplace() {
  return loadSource("marketplace", (topicId) => Promise.all([api.marketplaceProducts(topicId), api.marketplaceStats(topicId)]), ([productPayload, stats]) => { state.marketplaceProducts = productPayload.items || []; state.marketplaceStats = stats; });
}
async function refreshTrend({ clear = true } = {}) {
  if (!state.activeTopicId) { clearTopicData(); state.sourceStates = newSourceStates(); renderAllData(); return; }
  if (clear) { clearTopicData(); state.sourceStates = newSourceStates(true); renderAllData(); }
  await Promise.allSettled([loadYouTube(), loadMaps(), loadSocial(), loadMarketplace()]);
}
async function selectTopic(id) {
  if (!id || id === state.activeTopicId) return;
  state.activeTopicId = id; state.videoType = "";
  document.querySelectorAll("#type-filters button").forEach((button) => button.classList.toggle("active", button.dataset.type === ""));
  renderTopics(); renderActiveSource(); await refreshTrend();
}
function resetDialog() { $("topic-form").reset(); $("topic-city").value = "Bandung"; $("suggestion-box").hidden = true; $("topic-error").hidden = true; $("save-topic").disabled = true; state.suggestion = null; }
function openDialog() { resetDialog(); $("topic-dialog").showModal(); requestAnimationFrame(() => $("topic-name").focus()); }
function closeDialog() { $("topic-dialog").close(); }
function escapeTag(value) { return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[character])); }
function renderSuggestion(suggestion) {
  const tags = (values) => values.map((value) => `<span>${escapeTag(value)}</span>`).join("");
  $("keyword-preview").innerHTML = tags(suggestion.keywords); $("terms-preview").innerHTML = tags(suggestion.product_terms); $("topic-category").value = suggestion.category;
  $("suggestion-box").hidden = false; $("save-topic").disabled = false;
}
async function suggestTopic() {
  const name = $("topic-name").value.trim(); if (name.length < 2) { $("topic-name").reportValidity(); return; }
  const button = $("suggest-button"); button.disabled = true; button.textContent = "Menyiapkan…";
  try { state.suggestion = await api.suggestTopic(name); renderSuggestion(state.suggestion); $("topic-error").hidden = true; }
  catch (error) { $("topic-error").textContent = error.message; $("topic-error").hidden = false; }
  finally { button.disabled = false; button.textContent = "Buat kata pencarian"; }
}
async function createTopic(event) {
  event.preventDefault(); if (!state.suggestion) { await suggestTopic(); if (!state.suggestion) return; }
  const save = $("save-topic"); save.disabled = true; save.textContent = "Mengaktifkan…";
  const payload = { name: $("topic-name").value.trim(), keywords: state.suggestion.keywords, product_terms: state.suggestion.product_terms, exclude_terms: state.suggestion.exclude_terms || [], category: $("topic-category").value, cities: [$("topic-city").value.trim()] };
  try {
    const topic = await api.createTopic(payload); closeDialog(); await loadTopics(topic.id);
    clearTopicData(); state.sourceStates = newSourceStates(true); renderAllData(); renderActiveSource();
    showBanner("discovering", `Menyiapkan sumber untuk “${topic.name}”. Data akan masuk bertahap tanpa mengosongkan dashboard.`);
    clearTimeout(topicRefreshTimer); topicRefreshTimer = setTimeout(async () => { await loadTopics(topic.id); await refreshTrend({ clear: false }); }, 5000);
  } catch (error) { $("topic-error").textContent = error.message; $("topic-error").hidden = false; }
  finally { save.disabled = false; save.textContent = "Mulai pantau"; }
}
function connectStream() {
  stream?.close(); stream = new EventSource("/api/stream");
  stream.onopen = () => setConnection(true);
  stream.onerror = () => setConnection(false);
  stream.addEventListener("trend_tick", (event) => { const tick = JSON.parse(event.data); if (tick.topic_id !== state.activeTopicId) return; $("live-ticker").textContent = `+${new Intl.NumberFormat("id-ID").format(tick.views_gain_since_last || 0)} sejak snapshot`; loadYouTube(); });
  stream.addEventListener("topic_status", async (event) => { const update = JSON.parse(event.data); await loadTopics(update.topic_id === state.activeTopicId ? update.topic_id : ""); if (update.topic_id === state.activeTopicId) { showBanner(update.status, update.message); await refreshTrend({ clear: false }); } });
  stream.addEventListener("social_sentiment_updated", async (event) => { const update = JSON.parse(event.data); if (update.topic_id === state.activeTopicId) await loadSocial(); else await loadTopics(); });
}
function chooseSource(source) {
  state.activeSource = source; renderActiveSource();
  if (["tiktok", "instagram", "facebook"].includes(source)) renderSocial();
  renderSourceNavigation(); renderSourceProgress();
}
function bindControls() {
  $("topic-tabs").addEventListener("click", (event) => { const button = event.target.closest("button[data-topic-id]"); if (button) selectTopic(button.dataset.topicId); });
  $("source-nav").addEventListener("click", (event) => { const button = event.target.closest("button[data-source]"); if (button) chooseSource(button.dataset.source); });
  $("overview-view").addEventListener("click", (event) => { const button = event.target.closest("button[data-source-jump]"); if (button) chooseSource(button.dataset.sourceJump); });
  $("add-topic-button").addEventListener("click", openDialog); $("close-dialog").addEventListener("click", closeDialog); $("cancel-topic").addEventListener("click", closeDialog); $("suggest-button").addEventListener("click", suggestTopic);
  $("topic-name").addEventListener("input", () => { state.suggestion = null; $("suggestion-box").hidden = true; $("save-topic").disabled = true; });
  $("topic-form").addEventListener("submit", createTopic); $("topic-dialog").addEventListener("click", (event) => { if (event.target === $("topic-dialog")) closeDialog(); });
  $("type-filters").addEventListener("click", async (event) => { const button = event.target.closest("button[data-type]"); if (!button) return; state.videoType = button.dataset.type; document.querySelectorAll("#type-filters button").forEach((item) => item.classList.toggle("active", item === button)); await loadVideos(); });
  $("video-sort").addEventListener("change", async (event) => { state.videoSort = event.target.value; await loadVideos(); });
}
async function init() {
  bindControls();
  try { const [health, usage] = await Promise.all([api.health(), api.usage()]); state.health = health; state.usage = usage; renderHealth(); renderUsage(); renderActiveSource(); await loadTopics(); await refreshTrend(); window.setInterval(refreshUsage, 30000); }
  catch (error) { showToast(`Aplikasi belum siap: ${error.message}`); }
  connectStream();
}
init();
