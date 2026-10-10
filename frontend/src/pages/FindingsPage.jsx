import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { AnalystField, FindingsList, Notice, useAnalystName } from "../components/Findings.jsx";

const FILTERS = [
  ["", "All"],
  ["possible_gap", "Possible gap"],
  ["not_checkable", "Not checkable"],
  ["ok", "OK"],
];

export default function FindingsPage() {
  const [status, setStatus] = useState("");
  const [findings, setFindings] = useState(null);
  const [error, setError] = useState(null);
  const [analyst, setAnalyst] = useAnalystName();

  const load = useCallback(async () => {
    setError(null);
    setFindings(null);
    try {
      setFindings(await api.findings({ status }));
    } catch (e) {
      setError(e);
    }
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const onDecided = (id, d) =>
    setFindings((fs) => fs.map((f) => (f.id === id ? { ...f, decision: d } : f)));

  return (
    <section>
      <h1>Findings</h1>
      <p className="lead">Latest stored run for each site. Each result shows when it was computed.</p>
      <div className="toolbar">
        <div className="filters" role="group" aria-label="Status filter">
          {FILTERS.map(([value, label]) => (
            <button key={value || "all"} type="button"
                    className={`chip ${status === value ? "active" : ""}`}
                    aria-pressed={status === value} onClick={() => setStatus(value)}>
              {label}
            </button>
          ))}
        </div>
        <AnalystField analyst={analyst} setAnalyst={setAnalyst} />
      </div>

      {error && (
        <Notice kind="error">
          Could not load findings: {error.message}{" "}
          <button type="button" className="linkbtn" onClick={load}>Retry</button>
        </Notice>
      )}
      {!error && findings === null && <Notice>Loading findings…</Notice>}
      {findings && findings.length === 0 && (
        <Notice>
          {status
            ? "No findings with this status."
            : "No findings yet. Run a check on the Check screen, or run scripts/crawl_all.py on the server."}
        </Notice>
      )}
      {findings && findings.length > 0 && (
        <FindingsList findings={findings} analyst={analyst} onDecided={onDecided} />
      )}
    </section>
  );
}
