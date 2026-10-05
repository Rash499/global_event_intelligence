import AnimatedNumber from "./ui/AnimatedNumber";

const isFromLastWeek = (event) => {
  const eventTime = new Date(event.event_time).getTime();
  const now = Date.now();
  const oneWeekAgo = now - 7 * 24 * 60 * 60 * 1000;

  return (
    !Number.isNaN(eventTime) &&
    eventTime >= oneWeekAgo &&
    eventTime <= now
  );
};

export default function StatsBar({ events }) {
  const recentEvents = events.filter(isFromLastWeek);

  const majorEvents = recentEvents.filter(
    (event) => event.importance >= 8
  ).length;

  const countries = new Set(
    recentEvents
      .map((event) => event.country_code)
      .filter(Boolean)
  ).size;

  const categories = new Set(
    recentEvents
      .map((event) => event.category)
      .filter(Boolean)
  ).size;

  return (
    <section className="stats" aria-label="Global event summary">
      <div className="stat-card stat-card-events" style={{ "--i": 0 }}>
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">◈</span>
          <span className="stat-kicker">Live index</span>
        </div>
        <strong><AnimatedNumber value={recentEvents.length} /></strong>
        <span>Events last 7 days</span>
        <small>Current global activity</small>
      </div>

      <div className="stat-card stat-card-major" style={{ "--i": 1 }}>
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">!</span>
          <span className="stat-kicker">Priority</span>
        </div>
        <strong><AnimatedNumber value={majorEvents} /></strong>
        <span>Major events last 7 days</span>
        <small>Importance score 8+</small>
      </div>

      <div className="stat-card stat-card-countries" style={{ "--i": 2 }}>
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">◎</span>
          <span className="stat-kicker">Reach</span>
        </div>
        <strong><AnimatedNumber value={countries} /></strong>
        <span>Countries last 7 days</span>
        <small>Geographies represented</small>
      </div>

      <div className="stat-card stat-card-categories" style={{ "--i": 3 }}>
        <div className="stat-topline">
          <span className="stat-icon" aria-hidden="true">⌘</span>
          <span className="stat-kicker">Signal mix</span>
        </div>
        <strong><AnimatedNumber value={categories} /></strong>
        <span>Categories last 7 days</span>
        <small>Distinct event themes</small>
      </div>
    </section>
  );
}