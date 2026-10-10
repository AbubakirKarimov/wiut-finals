import { useEffect, useState } from "react";
import { api, formatTime } from "../api.js";
import { Notice, StatusBadge } from "../components/Findings.jsx";

function fmt(v, unit = "") {
  if (v === null || v === undefined) return "no data";
  if (typeof v === "number") return `${v}${unit}`;
  return v;
}

function pct(v) {
  return typeof v === "number" ? `${Math.round(v * 1000) / 10}%` : fmt(v);
}

function Stat({ label, value, note }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

function Metrics({ m }) {
  const p = m.precision_possible_gap_vs_labels;
  const a = m.analyst_confirmation_rate;
  const cost = m.llm.avg_cost_usd_per_check;
  const c = m.consistency;
  return (
    <div className="stats" data-testid="metrics">
      <Stat label="Checks completed" value={m.checks_completed} />
      <Stat label="Latency p50" value={fmt(m.latency_seconds.p50, " s")} note={`${m.latency_seconds.runs} run(s)`} />
      <Stat label="Latency p95" value={fmt(m.latency_seconds.p95, " s")} />
      <Stat label="Avg tokens per check" value={fmt(m.llm.avg_tokens_per_check)}
            note={`${m.llm.api_calls} API call(s), ${m.llm.cache_hits} cache hit(s)`} />
      <Stat label="Avg cost per check" value={typeof cost === "number" ? `$${cost}` : cost}
            note={cost === "not set" ? "LLM prices are not set in the server config" : "from token logs × configured prices"} />
      <Stat label="Precision (possible gap vs. team labels)" value={pct(p.value)}
            note={p.detail || (p.predicted_gaps != null ? `${p.true_positives}/${p.predicted_gaps} flagged gaps labelled as gaps` : "")} />
      <Stat label="Analyst confirmation rate" value={pct(a.value)}
            note={`${a.decided} possible gap(s) decided`} />
      <Stat label="Consistency (repeat runs agree on status)" value={pct(c.value)}
            note={c.requirements
              ? `${c.requirements} requirement(s) on ${c.banks} bank(s), same pages, fresh LLM answers; evidence quotes identical ${pct(c.quote_agreement)}`
              : c.detail} />
      <Stat label="Findings by status"
            value={`${m.findings_by_status.possible_gap} / ${m.findings_by_status.not_checkable} / ${m.findings_by_status.ok}`}
            note="possible gap / not checkable / ok" />
    </div>
  );
}

export default function AuditPage() {
  const [decisions, setDecisions] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([api.decisions(), api.metrics()])
      .then(([d, m]) => {
        setDecisions(d);
        setMetrics(m);
      })
      .catch(setError);
  }, []);

  if (error) return <Notice kind="error">Could not load the audit log: {error.message}</Notice>;
  if (!decisions || !metrics) return <Notice>Loading…</Notice>;

  return (
    <section>
      <h1>Audit &amp; Metrics</h1>
      <h2>Metrics</h2>
      <Metrics m={metrics} />

      <h2>Decision log</h2>
      {decisions.length === 0 ? (
        <Notice>No analyst decisions yet. Confirm or reject findings on the Findings screen.</Notice>
      ) : (
        <div className="tablewrap">
          <table className="log" data-testid="decision-log">
            <thead>
              <tr>
                <th>When</th><th>Analyst</th><th>Verdict</th><th>Bank</th>
                <th>Requirement</th><th>Finding</th><th>Comment</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d) => (
                <tr key={d.id}>
                  <td data-label="When">{formatTime(d.decided_at)}</td>
                  <td data-label="Analyst">{d.analyst}</td>
                  <td data-label="Verdict">
                    <span className={`verdict verdict-${d.verdict}`}>{d.verdict}</span>
                  </td>
                  <td data-label="Bank">{d.bank_name || "no data"}</td>
                  <td data-label="Requirement">{d.req_text_en || d.requirement_id || "no data"}</td>
                  <td data-label="Finding">{d.finding_status ? <StatusBadge status={d.finding_status} /> : "no data"}</td>
                  <td data-label="Comment">{d.comment || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
