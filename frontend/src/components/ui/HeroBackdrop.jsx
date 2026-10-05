/** Decorative animated backdrop for the overview hero. Pure CSS, no assets. */
export default function HeroBackdrop() {
  return (
    <div className="hero-backdrop" aria-hidden="true">
      <span className="hero-orb hero-orb-a" />
      <span className="hero-orb hero-orb-b" />
      <span className="hero-grid" />
      <span className="hero-scan" />
    </div>
  );
}
