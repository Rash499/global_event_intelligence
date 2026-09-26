import axios from "axios";

export const api = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 30000,
});

export const getLatestEvents = async (limit = 300, userId) => {
  const response = await api.get("/events/latest", {
    params: { limit, ...(userId ? { user_id: userId } : {}) },
  });
  return response.data;
};

export const getEventHistory = async (limit = 1000, userId) => {
  const response = await api.get("/events/history", {
    params: { limit, ...(userId ? { user_id: userId } : {}) },
  });
  return response.data;
};

export const getCountryEvents = async (countryCode, userId) => {
  const response = await api.get(`/countries/${countryCode}`, {
    params: userId ? { user_id: userId } : {},
  });
  return response.data;
};

export const getEvent = async (eventId, userId) => {
  const response = await api.get(`/events/${eventId}`, {
    params: userId ? { user_id: userId } : {},
  });
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

export const getEventInteractionSummary = async (eventIds, userId) => {
  const response = await api.get("/interactions/summary", {
    params: {
      event_ids: eventIds.join(","),
      user_id: userId,
    },
  });

  return response.data;
};

export const getEventInteractions = async (eventId, userId) => {
  const response = await api.get(`/events/${eventId}/interactions`, {
    params: { user_id: userId },
  });

  return response.data;
};

export const toggleEventLike = async (eventId, userId) => {
  const response = await api.post(`/events/${eventId}/like`, {
    user_id: userId,
  });

  return response.data;
};

export const addEventComment = async (eventId, { userId, body, author }) => {
  const response = await api.post(`/events/${eventId}/comments`, {
    user_id: userId,
    body,
    author,
  });

  return response.data;
};

export const deleteEventComment = async (eventId, commentId, userId) => {
  const response = await api.delete(
    `/events/${eventId}/comments/${commentId}`,
    { params: { user_id: userId } }
  );

  return response.data;
};

