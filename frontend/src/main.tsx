import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { CallerApp } from "./caller/CallerApp";
import { DashboardApp } from "./dashboard/DashboardApp";
import "./styles.css";

// Minimal path-based routing: "/dashboard" shows the responder board, else caller.
function Root(): JSX.Element {
  const isDashboard = window.location.pathname.startsWith("/dashboard");
  return isDashboard ? <DashboardApp /> : <CallerApp />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
