/**
 * Re-mounts its subtree when `viewKey` changes so the CSS entrance animation
 * replays on every navigation. Motion is disabled globally for reduced-motion users.
 */
export default function PageTransition({ viewKey, children }) {
  return (
    <div key={viewKey} className="page-transition" data-view={viewKey}>
      {children}
    </div>
  );
}
