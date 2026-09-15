export type EventItem = {
  id: number;
  title: string;
  summary: string;
  category: string;
  country: string | null;
  country_code: string | null;
  latitude: number | null;
  longitude: number | null;
  importance: number;
  confidence: number;
  event_time: string;
};
