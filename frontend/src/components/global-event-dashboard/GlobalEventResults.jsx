import EventDetails from "../EventDetails";
import EventHistoryTable from "./EventHistoryTable";

export default function GlobalEventResults({ events, selectedEvent, onSelect, onBack }) {
  if (selectedEvent) {
    return <EventDetails event={selectedEvent} onBack={onBack} />;
  }

  return <EventHistoryTable events={events} onSelect={onSelect} />;
}
