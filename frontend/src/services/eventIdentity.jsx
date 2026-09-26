const USER_KEY = "gei.interaction.user_id";
const AUTHOR_KEY = "gei.interaction.author_name";

export const DEFAULT_AUTHOR_NAME = "Guest analyst";

const readValue = (key) => {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};

const writeValue = (key, value) => {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable (private browsing); interactions still work
    // for the current session.
  }
};

const createUserId = () =>
  `gei-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

export function getLocalUserId() {
  const existing = readValue(USER_KEY);

  if (existing) return existing;

  const created = createUserId();
  writeValue(USER_KEY, created);

  return created;
}

export function getAuthorName() {
  return readValue(AUTHOR_KEY) || DEFAULT_AUTHOR_NAME;
}

export function setAuthorName(name) {
  const trimmed = (name || "").trim();

  if (!trimmed) return;

  writeValue(AUTHOR_KEY, trimmed.slice(0, 40));
}
