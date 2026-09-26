import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { InteractionProvider } from "./components/interactions/InteractionProvider";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <InteractionProvider>
      <App />
    </InteractionProvider>
  </React.StrictMode>
);
