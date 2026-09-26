import {
  useEventInteraction,
  useEventInteractions,
} from "./InteractionProvider";

function LikeIcon() {
  return (
    <svg
      className="interaction-icon"
      viewBox="0 0 24 24"
      width="15"
      height="15"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M12 20.7C6.4 17.3 3 13.6 3 9.9 3 7.2 5.1 5 7.8 5c1.7 0 3.2.9 4.2 2.3C13 5.9 14.5 5 16.2 5 18.9 5 21 7.2 21 9.9c0 3.7-3.4 7.4-9 10.8z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CommentIcon() {
  return (
    <svg
      className="interaction-icon"
      viewBox="0 0 24 24"
      width="14"
      height="14"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9.6L5 20.6V5a1 1 0 0 1 1-1zm2 3v2h12V7H6zm0 4v2h9v-2H6z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function EventInteractionBar({ event, showComments, onToggleComments }) {
  const interaction = useEventInteraction(event);
  const { toggleLike } = useEventInteractions();

  const handleLike = (clickEvent) => {
    clickEvent.stopPropagation();
    toggleLike(event);
  };

  const handleComments = (clickEvent) => {
    clickEvent.stopPropagation();
    onToggleComments?.();
  };

  return (
    <div className="interaction-bar">
      <button
        type="button"
        className={`interaction-button interaction-like${
          interaction.liked ? " active" : ""
        }`}
        aria-pressed={interaction.liked}
        aria-label={`Like this event. ${interaction.like_count} likes`}
        title={interaction.liked ? "Remove your like" : "Like this event"}
        disabled={interaction.pendingLike}
        onClick={handleLike}
      >
        <LikeIcon />
        <span className="interaction-count">{interaction.like_count}</span>
      </button>

      <button
        type="button"
        className={`interaction-button interaction-comments${
          showComments ? " active" : ""
        }`}
        aria-expanded={Boolean(showComments)}
        aria-label={`Comments. ${interaction.comment_count} comments`}
        title={showComments ? "Hide comments" : "Show comments"}
        onClick={handleComments}
      >
        <CommentIcon />
        <span className="interaction-count">{interaction.comment_count}</span>
      </button>
    </div>
  );
}
