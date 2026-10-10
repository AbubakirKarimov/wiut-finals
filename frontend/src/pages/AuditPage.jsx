import { useEffect, useState } from "react";
import { api, formatTime } from "../api.js";
import { Notice, StatusBadge } from "../components/Findings.jsx";

function fmt(v, unit = "") {
  if (v === null || v === undefined || v === "no data") return "n/a";
  if (typeof v === "number") return `${v}${unit}`;
  return v;
}

function pct(v) {
  return typeof v === "number" ? `${Math.round(v * 1000) / 10}%` : fmt(v);
}

function usd(v) {
  return typeof v === "number" ? `$${v.toFixed(6).replace(/0+$/, "").replace(/\.$/, "")}` : fmt(v);
}

function Stat({ label, value, note, testid }) {
  return (
    <div className="stat" data-testid={testid}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

const MIN_REVIEWED = 5;

// From eval/audit_report.md (summary and "Fixes applied"), 2026-10-10. Static text.
const AUDIT_FAILURES = [
  "Quotes: 27 of 27 audited quotes were verbatim on the stored page and on the live page.",
  "Coverage: in 3 of the 4 gaps with strong counter-evidence, the evidence was on deposit or loan pages the 15-page crawl never read (now: section pages are fetched first, and a gap needs the relevant section read).",
  "Keyword matching missed natural wording and the literal required link text (fixed: stem matching across scripts).",
  "LLM stability was not measured: the provider's daily token quota ran out during the audit.",
  "Prompt injection: a page that plants the sentence it asks the model to quote would still pass verification (known limitation).",
  "JavaScript-only sites need a headless browser; without it they are not checkable.",
  "The page store keeps one version per URL, so a later crawl can replace the text an old quote was verified against (not fixed).",
];

function Metrics({ m }) {
  const a = m.precision_possible_gap_from_decisions;
  const d = m.decided_by;
  const r = m.decided_by_replay || {};
  const u = m.llm_usage;
  const c = m.consistency;
  const n = a.decided;
  return (
    <>
      <h2>Analyst review</h2>
      <div className="stats">
        <Stat testid="precision" label="Possible gaps confirmed by analysts"
              value={n ? `${a.confirmed} of ${n} confirmed` : "n/a"}
              note={n < MIN_REVIEWED
                ? `not enough data (n = ${n} reviewed; at least ${MIN_REVIEWED} needed)`
                : `n = ${n} reviewed possible gaps · ${typeof a.value === "number" ? `precision ${pct(a.value)}` : a.value}`} />
        <Stat label="Findings by status"
              value={`${m.findings_by_status.possible_gap} / ${m.findings_by_status.not_checkable} / ${m.findings_by_status.ok}`}
              note="possible gap / not checkable / ok (all stored runs)" />
      </div>

      <h2>Who decided: code vs LLM-assisted</h2>
      <div className="stats" data-testid="decided-split">
        <Stat label="Shown findings decided by code" value={pct(d.share_code)}
              note={d.recorded
                ? `${d.code} code · ${d.llm_assisted} LLM-assisted · ${d.not_recorded} not recorded`
                : `n/a: the ${d.not_recorded} shown finding(s) were stored before this was recorded`} />
        <Stat label="Current checks replayed on stored pages" value={pct(r.share_code)}
              note={r.findings
                ? `${r.decided_by.code} of ${r.findings} findings decided by code on ${r.banks} banks (no LLM calls; eval/replay_stored.py, ${String(r.generated_at).slice(0, 10)})`
                : "n/a: replay not run"} />
      </div>

      <h2>Speed and cost</h2>
      <div className="stats" data-testid="metrics">
        <Stat label="Checks completed" value={m.checks_completed} />
        <Stat label="Median time per site check" value={fmt(m.latency_seconds.p50, " s")}
              note={`p95 ${fmt(m.latency_seconds.p95, " s")} · ${m.latency_seconds.runs} run(s)`} />
        <Stat label="Median LLM call latency" value={fmt(u.median_call_latency_ms, " ms")}
              note={`${u.api_calls ?? 0} API call(s), ${u.cache_hits ?? 0} cache hit(s)`} />
        <Stat label="LLM calls per run" value={fmt(u.calls_per_run)} note={`${u.runs} run(s)`} />
        <Stat label="Tokens per run" value={fmt(u.tokens_per_run)} note="input + output, API calls only" />
        <Stat label="Estimated cost per requirement check" value={usd(u.cost_usd_per_check)}
              note={`per site run ${usd(u.cost_usd_per_run)} · list price from server config`} />
        <Stat label="Consistency (repeat runs agree)" value={pct(c.value)}
              note={c.requirements ? `${c.requirements} requirement(s) on ${c.banks} bank(s)` : c.detail} />
      </div>

      <h2>Known failure cases</h2>
      <p className="muted small">From the audit (eval/audit_report.md, 2026-10-10); static text.</p>
      <ul className="failures" data-testid="known-failures">
        {AUDIT_FAILURES.map((t) => <li key={t}>{t}</li>)}
      </ul>
    </>
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
  if (!decisions || !metrics) {
    return (
      <section aria-busy="true">
        <h1>Audit &amp; Metrics</h1>
        <div className="stats">{[1, 2, 3, 4].map((i) => <div key={i} className="stat skeleton"><div className="sk sk-line" /></div>)}</div>
      </section>
    );
  }

  return (
    <section>
      <h1>Audit &amp; Metrics</h1>
      <p className="lead">All figures are computed from stored runs, decisions and LLM call logs; &ldquo;n/a&rdquo; means no data.</p>
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
                <th>Requirement</th><th>Finding</th><th>Decided by</th><th>Comment</th>
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
                  <td data-label="Decided by">{d.decided_by === "llm_assisted" ? "LLM-assisted" : d.decided_by || "not recorded"}</td>
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
