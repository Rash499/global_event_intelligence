import axios from "axios";

export const api = axios.create({
  baseURL: "http://localhost:8000/api",
  timeout: 30000,
});

export const getLatestEvents = async (limit = 300) => {
  const response = await api.get(`/events/latest?limit=${limit}`);
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