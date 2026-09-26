import EventDetails from "../EventDetails";
import EventHistoryGrid from "./EventHistoryGrid";

export default function GlobalEventResults({ events, selectedEvent, onSelect, onBack }) {
  if (selectedEvent) {
    return <EventDetails event={selectedEvent} onBack={onBack} />;
  }

  return <EventHistoryGrid events={events} onSelect={onSelect} />;
}
