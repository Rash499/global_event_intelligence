import { useEffect, useState } from "react";

import { formatRelativeTime } from "../../services/dateFormat.jsx";
import {
  DEFAULT_AUTHOR_NAME,
  getAuthorName,
  setAuthorName,
} from "../../services/eventIdentity.jsx";
import { useEventInteraction, useEventInteractions } from "./InteractionProvider";

export default function EventComments({ event, autoFocus = false }) {
  const interaction = useEventInteraction(event);
  const { userId, loadComments, postComment, removeComment } =
    useEventInteractions();
  const [author, setAuthor] = useState(() => getAuthorName());
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);

  useEffect(() => {
    loadComments(event.id);
  }, [event.id, loadComments]);

  const handleSubmit = async (submitEvent) => {
    submitEvent.preventDefault();

    const text = body.trim();

    if (!text || posting) return;

    const name = author.trim() || DEFAULT_AUTHOR_NAME;

    setPosting(true);

    const created = await postComment(event, text, name);

    if (created) {
      setAuthorName(name);
      setAuthor(name);
      setBody("");
    }

    setPosting(false);
  };

  return (
    <section className="event-comments" aria-label="Event comments">
      <form className="comment-composer" onSubmit={handleSubmit}>
        <input
          className="comment-author-input"
          value={author}
          maxLength={40}
          onChange={(changeEvent) => setAuthor(changeEvent.target.value)}
          aria-label="Display name"
          placeholder="Display name"
        />

        <input
          className="comment-input"
          value={body}
          maxLength={2000}
          autoFocus={autoFocus}
          onChange={(changeEvent) => setBody(changeEvent.target.value)}
          aria-label="Write a comment"
          placeholder="Add a comment about this event..."
        />

        <button
          type="submit"
          className="comment-submit"
          disabled={!body.trim() || posting}
        >
          {posting ? "Posting..." : "Post"}
        </button>
      </form>

      {interaction.error && (
        <p className="comment-status comment-status-error" role="alert">
          {interaction.error}
        </p>
      )}

      {interaction.loadingComments && !interaction.commentsLoaded ? (
        <p className="comment-status">Loading comments...</p>
      ) : interaction.comments.length ? (
        <ul className="comment-list">
          {interaction.comments.map((comment) => (
            <li className="comment-item" key={comment.id}>
              <span className="comment-avatar" aria-hidden="true">
                {(comment.author || DEFAULT_AUTHOR_NAME).slice(0, 1).toUpperCase()}
              </span>

              <div className="comment-copy">
                <div className="comment-meta">
                  <strong>{comment.author || DEFAULT_AUTHOR_NAME}</strong>
                  <span>{formatRelativeTime(comment.created_at)}</span>
                  {comment.user_id === userId && <em>you</em>}
                </div>
                <p>{comment.body}</p>
              </div>

              {comment.user_id === userId && (
                <button
                  type="button"
                  className="comment-delete"
                  onClick={() => removeComment(event.id, comment.id)}
                  aria-label="Delete your comment"
                  title="Delete your comment"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="comment-status">
          No comments yet. Start the discussion on this event.
        </p>
      )}
    </section>
  );
}
