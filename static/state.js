export const state = {
  topics: [], activeTopicId: "", metrics: null, videos: [], mapsPlaces: [], mapsFeed: [], socialPosts: [], socialStats: null, health: null, usage: null,
  activeSource: "overview", marketplaceProducts: [], marketplaceStats: null, videoType: "", videoSort: "gain", suggestion: null, charts: {},
  sourceStates: {
    youtube: { loading: false, loaded: false, error: "" },
    maps: { loading: false, loaded: false, error: "" },
    social: { loading: false, loaded: false, error: "" },
    marketplace: { loading: false, loaded: false, error: "" },
  },
};
