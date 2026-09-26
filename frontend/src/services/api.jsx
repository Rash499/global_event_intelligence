import axios from "axios";
import { getAuthToken } from "./authSession.jsx";

export const api = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 30000,
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
  const response = await api.get("/statistics/global");
  return response.data;
};

export const runIngestion = async () => {
  const response = await api.post(
    "/ingestion/run",
    {},
    {
      timeout: 300000,
    }
  );

  return response.data;
};

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

