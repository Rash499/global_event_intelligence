import EventDetails from "../EventDetails";
import EventList from "../EventList";

export default function GlobalEventResults({ events, selectedEvent, onSelect, onBack }) {
  if (selectedEvent) {
    return <EventDetails event={selectedEvent} onBack={onBack} />;
  }

  return <EventList events={events} onSelect={onSelect} />;
}
