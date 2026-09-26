import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  addEventComment,
  deleteEventComment,
  getEventInteractions,
  toggleEventLike,
} from "../../services/api.jsx";
import { getLocalUserId } from "../../services/eventIdentity.jsx";

const InteractionContext = createContext(null);

export const emptyInteraction = {
  like_count: 0,
  comment_count: 0,
  liked: false,
  comments: [],
  commentsLoaded: false,
  loadingComments: false,
  pendingLike: false,
  error: "",
};

const buildInteraction = (event) => ({
  ...emptyInteraction,
  like_count: Number(event?.like_count) || 0,
  comment_count: Number(event?.comment_count) || 0,
  liked: Boolean(event?.liked),
});

export function InteractionProvider({ children }) {
  const userId = useMemo(() => getLocalUserId(), []);
  const [interactions, setInteractions] = useState({});
  const interactionsRef = useRef(interactions);

  const updateInteraction = useCallback((eventId, changes) => {
    const key = String(eventId);
    const previous = interactionsRef.current[key] || emptyInteraction;
    const next =
      typeof changes === "function"
        ? changes(previous)
        : { ...previous, ...changes };

    if (next === previous) return;

    interactionsRef.current = { ...interactionsRef.current, [key]: next };
    setInteractions(interactionsRef.current);
  }, []);

  const toggleLike = useCallback(
    async (event) => {
      const eventId = event.id;
      const key = String(eventId);
      const base = interactionsRef.current[key] || buildInteraction(event);
      const nextLiked = !base.liked;
      const optimisticLikeCount = Math.max(
        0,
        base.like_count + (nextLiked ? 1 : -1)
      );

      updateInteraction(eventId, {
        ...base,
        liked: nextLiked,
        like_count: optimisticLikeCount,
        pendingLike: true,
        error: "",
      });

      try {
        const data = await toggleEventLike(eventId, userId);

        updateInteraction(eventId, {
          liked: Boolean(data.liked),
          like_count: Number(data.like_count ?? optimisticLikeCount),
          pendingLike: false,
        });
      } catch (error) {
        console.error("Failed to save like:", error);

        updateInteraction(eventId, {
          liked: base.liked,
          like_count: base.like_count,
          pendingLike: false,
          error: "Your like could not be saved.",
        });
      }
    },
    [updateInteraction, userId]
  );

  const loadComments = useCallback(
    async (eventId, { force = false } = {}) => {
      const key = String(eventId);
      const current = interactionsRef.current[key];

      if (current?.loadingComments) return;
      if (!force && current?.commentsLoaded) return;

      updateInteraction(eventId, { loadingComments: true, error: "" });

      try {
        const data = await getEventInteractions(eventId, userId);

        updateInteraction(eventId, {
          like_count: Number(data.like_count) || 0,
          comment_count: Number(data.comment_count) || 0,
          liked: Boolean(data.liked),
          comments: data.comments || [],
          commentsLoaded: true,
          loadingComments: false,
        });
      } catch (error) {
        console.error("Failed to load comments:", error);

        updateInteraction(eventId, {
          loadingComments: false,
          error: "Comments could not be loaded.",
        });
      }
    },
    [updateInteraction, userId]
  );

  const postComment = useCallback(
    async (event, body, author) => {
      try {
        const data = await addEventComment(event.id, {
          userId,
          body,
          author,
        });

        updateInteraction(event.id, (current) => ({
          ...current,
          comment_count: Number(data.comment_count ?? current.comment_count + 1),
          comments: [...current.comments, data.comment],
          error: "",
        }));

        return true;
      } catch (error) {
        console.error("Failed to post comment:", error);

        updateInteraction(event.id, {
          error: "Your comment could not be posted.",
        });

        return false;
      }
    },
    [updateInteraction, userId]
  );

  const removeComment = useCallback(
    async (eventId, commentId) => {
      try {
        const data = await deleteEventComment(eventId, commentId, userId);

        updateInteraction(eventId, (current) => ({
          ...current,
          comment_count: Number(
            data.comment_count ?? Math.max(0, current.comment_count - 1)
          ),
          comments: current.comments.filter(
            (comment) => comment.id !== commentId
          ),
          error: "",
        }));
      } catch (error) {
        console.error("Failed to delete comment:", error);

        updateInteraction(eventId, {
          error: "Your comment could not be removed.",
        });
      }
    },
    [updateInteraction, userId]
  );

  const syncEvent = useCallback(
    (event) => {
      if (!event?.id) return;

      updateInteraction(event.id, (current) => {
        if (current.pendingLike || current.commentsLoaded) return current;

        const nextLikeCount =
          Number(event.like_count ?? current.like_count) || 0;
        const nextCommentCount =
          Number(event.comment_count ?? current.comment_count) || 0;
        const nextLiked =
          typeof event.liked === "boolean" ? event.liked : current.liked;

        if (
          current.like_count === nextLikeCount &&
          current.comment_count === nextCommentCount &&
          current.liked === nextLiked
        ) {
          return current;
        }

        return {
          ...current,
          like_count: nextLikeCount,
          comment_count: nextCommentCount,
          liked: nextLiked,
        };
      });
    },
    [updateInteraction]
  );

  const value = useMemo(
    () => ({
      userId,
      interactions,
      toggleLike,
      loadComments,
      postComment,
      removeComment,
      syncEvent,
    }),
    [
      userId,
      interactions,
      toggleLike,
      loadComments,
      postComment,
      removeComment,
      syncEvent,
    ]
  );

  return (
    <InteractionContext.Provider value={value}>
      {children}
    </InteractionContext.Provider>
  );
}

export function useEventInteractions() {
  const context = useContext(InteractionContext);

  if (!context) {
    throw new Error(
      "useEventInteractions must be used inside an InteractionProvider"
    );
  }

  return context;
}

export function useEventInteraction(event) {
  const { interactions } = useEventInteractions();

  return interactions[String(event?.id)] || buildInteraction(event);
}
