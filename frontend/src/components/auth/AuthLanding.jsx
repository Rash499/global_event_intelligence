import { useEffect, useState } from "react";

import Globe from "../Globe";
import { useAuth } from "./AuthContext";
import { getEventHistory } from "../../services/api.jsx";

function getRequestError(error) {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join(" ");
  if (typeof detail === "string") return detail;
  return "We could not connect to the intelligence service. Check that the backend is running.";
}

export default function AuthLanding() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState("login");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [events, setEvents] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getEventHistory(1000)
      .then((data) => {
        if (active) setEvents(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const handleSubmit = async (submitEvent) => {
    submitEvent.preventDefault();
    if (submitting) return;

    setError("");
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register({
          display_name: displayName.trim(),
          email: email.trim(),
          password,
        });
      } else {
        await login({ email: email.trim(), password });
      }
    } catch (requestError) {
      setError(getRequestError(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  const handleModeChange = (nextMode) => {
    setMode(nextMode);
    setError("");
  };

  return (
    <main className="auth-page">
      <section className="auth-showcase" aria-labelledby="auth-title">
        <div className="auth-brand">
          <span className="auth-brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>GLOBAL EVENT INTELLIGENCE</span>
        </div>

        <div className="auth-copy">
          <p className="auth-eyebrow">A WORLD IN MOTION</p>
          <h1 id="auth-title">See the signals.<br />Understand the story.</h1>
          <p className="auth-description">
            A live view of major events, emerging risks, and the connections shaping today.
          </p>
        </div>

        <div className="auth-globe-stage" aria-label="Live global event map preview">
          <Globe
            mode="events"
            events={events}
            weather={[]}
            onSelectEvent={() => {}}
            onSelectWeather={() => {}}
            onSelectCountry={() => {}}
          />
          <div className="auth-globe-overlay" aria-hidden="true" />
          <div className="auth-map-caption">
            <span className="auth-live-dot" />
            <span>GLOBAL EVENT MAP</span>
            <span className="auth-caption-count">{events.length.toLocaleString()} signals</span>
          </div>
        </div>

        <div className="auth-showcase-footer">
          <span>WORLDWIDE COVERAGE</span>
          <span>NEWS · WEATHER · CONTEXT</span>
        </div>
      </section>

      <section className="auth-access" aria-label="Account access">
        <div className="auth-form-wrap">
          <p className="auth-form-eyebrow">YOUR INTELLIGENCE DESK</p>
          <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
          <p className="auth-form-intro">
            {mode === "login"
              ? "Sign in to follow events and join the discussion."
              : "Register to like, comment, and follow the global feed."}
          </p>

          <div className="auth-mode-switch" role="tablist" aria-label="Account action">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "login"}
              className={mode === "login" ? "active" : ""}
              onClick={() => handleModeChange("login")}
            >
              Sign in
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "register"}
              className={mode === "register" ? "active" : ""}
              onClick={() => handleModeChange("register")}
            >
              Register
            </button>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            {mode === "register" && (
              <label>
                <span>Name</span>
                <input
                  type="text"
                  autoComplete="name"
                  maxLength={60}
                  required
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Your name"
                />
              </label>
            )}
            <label>
              <span>Email</span>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label>
              <span>Password</span>
              <input
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                minLength={mode === "register" ? 8 : undefined}
                maxLength={128}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={mode === "register" ? "At least 8 characters" : "Your password"}
              />
            </label>

            {error && <p className="auth-error" role="alert">{error}</p>}

            <button className="auth-submit" type="submit" disabled={submitting}>
              {submitting
                ? "Please wait..."
                : mode === "login"
                  ? "Sign in to the map"
                  : "Create account"}
              <span aria-hidden="true">→</span>
            </button>
          </form>

          <p className="auth-access-note">
            Sign in to open the event map and join discussions. Registered accounts are required to like or comment.
          </p>
        </div>
        <div className="auth-access-footer">
          <span>GLOBAL EVENT INTELLIGENCE</span>
          <span>FASTAPI · SQLITE · LIVE SOURCES</span>
        </div>
      </section>
    </main>
  );
}