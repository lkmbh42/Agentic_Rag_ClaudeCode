import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// Self-hosted type (bundled into the build — no font CDN, air-gap safe).
// Latin subsets cover German (ä ö ü ß are Latin-1).
import "@fontsource/fira-sans/latin-400.css";
import "@fontsource/fira-sans/latin-500.css";
import "@fontsource/fira-sans/latin-600.css";
import "@fontsource/fira-sans/latin-700.css";
import "@fontsource/fira-mono/latin-400.css";
import "@fontsource/fira-mono/latin-500.css";
import "@fontsource/literata/latin-400.css";
import "@fontsource/literata/latin-400-italic.css";
import "@fontsource/literata/latin-600.css";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
