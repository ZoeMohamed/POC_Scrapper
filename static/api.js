async function request(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) } });
  if (!response.ok) {
    let detail = `Permintaan gagal (${response.status})`;
    try { const payload = await response.json(); detail = payload.detail || detail; } catch { /* not JSON */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}
function query(params) { const search = new URLSearchParams(); Object.entries(params).forEach(([key, value]) => { if (value !== "" && value !== null && value !== undefined) search.set(key, String(value)); }); return search.toString(); }
export const api = {
  health: () => request("/api/health"), usage: () => request("/api/usage"), topics: () => request("/api/topics"),
  suggestTopic: (name) => request("/api/topics/suggest", { method: "POST", body: JSON.stringify({ name }) }),
  createTopic: (payload) => request("/api/topics", { method: "POST", body: JSON.stringify(payload) }),
  trend: (topicId) => request(`/api/trend?${query({ topic_id: topicId })}`),
  videos: (topicId, sort, type) => request(`/api/trend/videos?${query({ topic_id: topicId, sort, type })}`),
  mapsPlaces: (topicId) => request(`/api/maps/places?${query({ topic_id: topicId })}`),
  mapsFeed: (topicId, limit = 30) => request(`/api/maps/feed?${query({ topic_id: topicId, limit })}`),
  socialFeed: (topicId, platform, limit = 100) => request(`/api/social/feed?${query({ topic_id: topicId, platform, limit })}`),
  socialStats: (topicId) => request(`/api/social/stats?${query({ topic_id: topicId })}`),
  marketplaceProducts: (topicId, platform = "shopee", limit = 100) => request(`/api/marketplace/products?${query({ topic_id: topicId, platform, limit })}`),
  marketplaceStats: (topicId, platform = "shopee") => request(`/api/marketplace/stats?${query({ topic_id: topicId, platform })}`),
};
