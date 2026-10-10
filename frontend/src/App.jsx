import { useEffect, useState } from "react";
import CheckPage from "./pages/CheckPage.jsx";
import FindingsPage from "./pages/FindingsPage.jsx";
import AuditPage from "./pages/AuditPage.jsx";

const ROUTES = {
  check: { label: "Check", Component: CheckPage },
  findings: { label: "Findings", Component: FindingsPage },
  audit: { label: "Audit & Metrics", Component: AuditPage },
};

function currentRoute() {
  const key = window.location.hash.replace(/^#\/?/, "");
  return ROUTES[key] ? key : "check";
}

export default function App() {
  const [route, setRoute] = useState(currentRoute);

  useEffect(() => {
    const onHash = () => setRoute(currentRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const { Component } = ROUTES[route];
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-name">ComplianceRadar</span>
          <span className="brand-sub">Possible gaps on bank websites · CBU Regulation 3030 &amp; State Language Law</span>
        </div>
        <nav className="tabs" aria-label="Main">
          {Object.entries(ROUTES).map(([key, r]) => (
            <a key={key} href={`#/${key}`} className={key === route ? "tab active" : "tab"}
               aria-current={key === route ? "page" : undefined}>
              {r.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="content">
        <Component />
      </main>
      <footer className="footer">
        Findings are <strong>possible gaps</strong> for review, not violations. A CBU analyst makes the decision.
      </footer>
    </div>
  );
}
