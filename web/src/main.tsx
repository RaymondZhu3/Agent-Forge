import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles/app.css";
import "./styles/night.css";
import "./styles/light.css";

// Theme: dark by default; the sidebar toggle remembers a choice per browser (storage may be unavailable).
try {
  if (localStorage.getItem("af-theme") === "light") document.documentElement.dataset.theme = "light";
} catch { /* private mode etc. */ }

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
