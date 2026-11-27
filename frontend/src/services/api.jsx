import axios from "axios";
import { getAuthToken } from "./authSession.jsx";

/**
 * The API base URL is configuration, not a hardcoded localhost address. In
 * development Vite proxies /api to the FastAPI server (see vite.config.ts), so
 * relative URLs keep working inside the sandbox preview and behind any origin.
 * Set VITE_API_BASE_URL to point the app at a remote backend.
 */
const API_BASE_URL = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "") || "";
const DEFAULT_TIMEOUT = Number(import.meta.env?.VITE_API_TIMEOUT_MS) || 30000;

export const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  timeout: DEFAULT_TIMEOUT,
});

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const registerAccount = async (account) => {
  const response = await api.post("/auth/register", account);
  return response.data;
};

export const loginAccount = async (credentials) => {
  const response = await api.post("/auth/login", credentials);
  return response.data;
};

export const getCurrentAccount = async () => {
  const response = await api.get("/auth/me");
  return response.data;
};

export const logoutAccount = async () => {
  await api.post("/auth/logout");
};

export const getLatestEvents = async (limit = 300) => {
  const response = await api.get("/events/latest", {
    params: { limit },
  });
  return response.data;
};

export const getEventHistory = async (limit = 1000) => {
  const response = await api.get("/events/history", {
    params: { limit },
  });
  return response.data;
};

export const getCountryEvents = async (countryCode) => {
  const response = await api.get(`/countries/${countryCode}`);
  return response.data;
};

export const getEvent = async (eventId) => {
  const response = await api.get(`/events/${eventId}`);
  return response.data;
};

export const getEventImage = async (eventId) => {
  const response = await api.get(`/events/${eventId}/image`);
  return response.data;
};

export const getGlobalStatistics = async () => {
  const response = await api.get("/statistics/overview");
  return response.data;
};

// The backend runs one ingestion cycle at a time and answers overlapping
// POSTs with 409. Share a single in-flight request across all callers
// (Collect News, per-provider Collect now, double clicks) so the UI never
// generates that conflict itself.
let ingestionInFlight = null;

function sharedIngestionRequest(url) {
  if (ingestionInFlight) return ingestionInFlight;
  ingestionInFlight = api
    .post(url, {}, { timeout: 300000 })
    .then((response) => response.data)
    .finally(() => {
      ingestionInFlight = null;
    });
  return ingestionInFlight;
}

export const runIngestion = async () => sharedIngestionRequest("/ingestion/run");

export const getGlobalWeather = async (locations) => {
  const response = await api.post(
    "/weather/global",
    { locations },
    { timeout: 120000 }
  );
  return response.data;
};

export const getEventInteractionSummary = async (eventIds) => {
  const response = await api.get("/interactions/summary", {
    params: { event_ids: eventIds.join(",") },
  });

  return response.data;
};

export const getEventInteractions = async (eventId) => {
  const response = await api.get(`/events/${eventId}/interactions`);

  return response.data;
};

export const toggleEventLike = async (eventId) => {
  const response = await api.post(`/events/${eventId}/like`);

  return response.data;
};

export const addEventComment = async (eventId, { body }) => {
  const response = await api.post(`/events/${eventId}/comments`, {
    body,
  });

  return response.data;
};

export const deleteEventComment = async (eventId, commentId) => {
  const response = await api.delete(`/events/${eventId}/comments/${commentId}`);

  return response.data;
};

// ---------------------------------------------------------------------------
// Phase 3 - Global Intelligence Assistant (RAG)
// ---------------------------------------------------------------------------

export const askAssistant = async (payload) => {
  // Grounded answers can take a while (local Ollama inference), so this call
  // gets a much larger timeout than the default 30s.
  const response = await api.post("/ai/query", payload, {
    timeout: 180000,
  });
  return response.data;
};

export const getAssistantStatus = async () => {
  const response = await api.get("/ai/status", { timeout: 15000 });
  return response.data;
};

export const getAssistantSuggestions = async () => {
  const response = await api.get("/ai/suggestions", { timeout: 15000 });
  return response.data;
};

export const runAssistantIndexing = async (options = {}) => {
  const response = await api.post("/ai/index", options, {
    timeout: 300000,
  });
  return response.data;
};



export const getHistoricalIntelligence = async (start, end, options = {}) => {
  const response = await api.get("/intelligence/history", {
    params: { start, end, ...options },
  });
  return response.data;
};

export const getHistoricalTrends = async (start, end, options = {}) => {
  const response = await api.get("/intelligence/trends", {
    params: { start, end, ...options },
  });
  return response.data;
};

export const getEventTimeline = async (eventId) => {
  const response = await api.get(`/intelligence/events/${eventId}/timeline`);
  return response.data;
};

export const getRelatedEvents = async (eventId) => {
  const response = await api.get(`/intelligence/events/${eventId}/related`);
  return response.data;
};

export const getEventSources = async (eventId) => {
  const response = await api.get(`/intelligence/events/${eventId}/sources`);
  return response.data;
};

export const compareHistoricalPeriods = async (periodA, periodB, scope = {}) => {
  const response = await api.post("/intelligence/compare", {
    period_a: periodA,
    period_b: periodB,
    scope,
  });
  return response.data;
};

/* ------------------------------------------------------------------ *
 * Intelligence platform endpoints (Phase 1-4)
 * ------------------------------------------------------------------ */

export const getDashboardOverview = async (hours = 24) => {
  const response = await api.get("/dashboard/overview", { params: { hours } });
  return response.data;
};

export const getMapEvents = async (params = {}) => {
  const response = await api.get("/map/events", { params });
  return response.data;
};

export const getIngestionStatus = async () => {
  const response = await api.get("/ingestion/status");
  return response.data;
};

export const getEventsPage = async (params = {}) => {
  const response = await api.get("/events", { params });
  return response.data;
};

export const getTaxonomy = async () => {
  const response = await api.get("/taxonomy");
  return response.data;
};

export const getProviders = async (history = false) => {
  const response = await api.get("/providers", { params: { history } });
  return response.data;
};

export const getProviderHistory = async (provider, limit = 50) => {
  const response = await api.get("/providers/history", { params: { provider, limit } });
  return response.data;
};

export const getCountryRisk = async (countryCode, days = 30) => {
  const response = await api.get(`/countries/${countryCode}/risk`, { params: { days } });
  return response.data;
};

export const getCountriesSummary = async (days = 30) => {
  const response = await api.get("/countries", { params: { days } });
  return response.data;
};

export const getConvergence = async (params = {}) => {
  const response = await api.get("/convergence", { params });
  return response.data;
};

export const getAnomalies = async (includeDismissed = false) => {
  const response = await api.get("/anomalies", { params: { include_dismissed: includeDismissed } });
  return response.data;
};

export const dismissAnomaly = async (anomalyId) => {
  await api.post(`/anomalies/${anomalyId}/dismiss`);
};

export const unifiedSearch = async (query) => {
  const response = await api.get("/search", { params: { q: query } });
  return response.data;
};

export const getEntities = async (params = {}) => {
  const response = await api.get("/entities", { params });
  return response.data;
};

export const getEntity = async (entityId) => {
  const response = await api.get(`/entities/${entityId}`);
  return response.data;
};

export const getAlerts = async (status) => {
  const response = await api.get("/alerts", { params: status ? { status } : {} });
  return response.data;
};

export const updateAlertStatus = async (alertId, status) => {
  const response = await api.post(`/alerts/${alertId}/status`, { status });
  return response.data;
};

export const getAlertRules = async () => {
  const response = await api.get("/alert-rules");
  return response.data;
};

export const createAlertRule = async (rule) => {
  const response = await api.post("/alert-rules", rule);
  return response.data;
};

export const deleteAlertRule = async (ruleId) => {
  await api.delete(`/alert-rules/${ruleId}`);
};

export const getSavedSearches = async () => {
  const response = await api.get("/saved-searches");
  return response.data;
};

export const createSavedSearch = async (payload) => {
  const response = await api.post("/saved-searches", payload);
  return response.data;
};

export const deleteSavedSearch = async (searchId) => {
  await api.delete(`/saved-searches/${searchId}`);
};

export const generateReport = async (payload) => {
  const response = await api.post("/reports", payload, { timeout: 120000 });
  return response.data;
};

export const listReports = async () => {
  const response = await api.get("/reports");
  return response.data;
};

export const reportExportUrl = (reportId, format = "csv") =>
  `${API_BASE_URL}/api/reports/${reportId}/export?format=${format}`;

export const getSystemStatus = async () => {
  const response = await api.get("/system/status");
  return response.data;
};

export const runProviderIngestion = async (provider) =>
  sharedIngestionRequest(
    `/ingestion/run?providers=${encodeURIComponent(provider)}`
  );
