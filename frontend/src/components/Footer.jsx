export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-glow" aria-hidden="true" />
      <div className="footer-inner">
        <div>
          <div className="footer-brand">GLOBAL INTELLIGENCE</div>
          <p>Real-time event discovery, analysis and grounded AI research in one workspace.</p>
        </div>
        <div className="footer-status">
          <span><i /> Systems operational</span>
          <small>GDELT · RSS · Ollama · FastAPI</small>
        </div>
        <div className="footer-meta">
          <span>Global Event Intelligence</span>
          <span>Built for research & situational awareness</span>
        </div>
      </div>
    </footer>
  );
}
