import { useState } from "react";
import { api, formatTime } from "../api.js";

const STATUS_TEXT = {
  ok: "OK",
  possible_gap: "Possible gap for review",
  not_checkable: "Not checkable",
};

const LANG_TEXT = { uz_latn: "Uzbek (Latin)", uz_cyrl: "Uzbek (Cyrillic)", ru: "Russian", other: "Other" };

// Plain-language headline for a not_checkable reason. The full reason is always shown too.
const REASONS = [
  [/relevant section not reached/i, "Relevant section not reached"],
  [/LLM timeout|rate limit|quota/i, "LLM quota exhausted or timed out – try again later"],
  [/bot protection|blocked/i, "Site blocked crawling (protection not bypassed)"],
  [/robots/i, "robots.txt does not allow crawling"],
  [/needs browser|browser could not|js_shell/i, "Site needs a browser (JavaScript-only)"],
  [/unreachable|timed out|connection/i, "Site unreachable"],
  [/only \d+ page\(s\) read/i, "Too few pages read to judge"],
  [/fetch error/i, "Some pages failed to load"],
  [/inner page|not a homepage page/i, "Found on an inner page, not on the homepage"],
  [/not as a link/i, "Text found, but not as a readable link"],
  [/repeats our own instructions|not found verbatim|answer rejected/i, "LLM answer rejected: its quote is not on the page"],
  [/code-level evidence of absence/i, "LLM did not confirm it – manual review needed"],
  [/LLM not configured/i, "LLM not configured on the server"],
  [/no link data/i, "No link data for these pages – re-crawl"],
  [/text is not in the visible page text|does not name the topic/i, "Link found, but its text cannot be quoted"],
];

export function reasonHeadline(reason) {
  if (!reason) return "No reason recorded";
  const hit = REASONS.find(([re]) => re.test(reason));
  return hit ? hit[1] : "Could not be decided automatically";
}

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_TEXT[status] || status}</span>;
}

export function DecidedBy({ value }) {
  const text = value === "code" ? "code" : value === "llm_assisted" ? "LLM-assisted" : "not recorded";
  return (
    <span className={`decidedby decidedby-${value || "none"}`} data-testid="decided-by"
          title={value === "llm_assisted"
            ? "An LLM answer influenced this status; its quote was verified by code"
            : value === "code" ? "Decided by deterministic code, no LLM" : "Stored before this was recorded"}>
      Decided by: {text}
    </span>
  );
}

export function Notice({ kind = "info", children }) {
  return (
    <div className={`notice notice-${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function useAnalystName() {
  const read = () => {
    try {
      return localStorage.getItem("analystName") || "";
    } catch {
      return "";
    }
  };
  const [name, setName] = useState(read);
  const update = (v) => {
    setName(v);
    try {
      localStorage.setItem("analystName", v);
    } catch {
      /* storage unavailable: keep in memory */
    }
  };
  return [name, update];
}

export function RunLabel({ run, live }) {
  if (!run || !run.finished_at) return null;
  if (live) return <span className="runlabel live">checked just now · {formatTime(run.finished_at)}</span>;
  return <span className="runlabel">pre-computed on {formatTime(run.finished_at)}</span>;
}

function DecisionBox({ finding, analyst, onDecided }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const decision = finding.decision;

  const decide = async (verdict) => {
    if (!analyst.trim()) {
      setError("Enter your analyst name above first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const d = await api.decide({ finding_id: finding.id, analyst, verdict, comment });
      setComment("");
      onDecided(finding.id, d);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="decision">
      {decision && (
        <p className={`decided decided-${decision.verdict}`} data-testid="decision-state">
          {decision.verdict === "confirmed" ? "Confirmed" : "Rejected"} by {decision.analyst}
          {" · "}{formatTime(decision.decided_at)}
          {decision.comment ? <span className="decided-comment">“{decision.comment}”</span> : null}
        </p>
      )}
      <label className="sr-only" htmlFor={`c-${finding.id}`}>Comment</label>
      <textarea id={`c-${finding.id}`} rows={2} placeholder="Comment (optional)"
                value={comment} onChange={(e) => setComment(e.target.value)} />
      <div className="decision-buttons">
        <button type="button" className="btn btn-confirm" disabled={busy}
                onClick={() => decide("confirmed")}>Confirm</button>
        <button type="button" className="btn btn-reject" disabled={busy}
                onClick={() => decide("rejected")}>Reject</button>
      </div>
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}

function PagesRead({ f, open }) {
  if (f.pages_read == null) return null;
  const pages = f.pages_detail || f.urls_read.map((url) => ({ url, language: "no data" }));
  return (
    <details className="urls" open={open} data-testid="pages-read">
      <summary>Pages read ({f.pages_read})</summary>
      <ul>
        {pages.map((p, i) => (
          <li key={`${p.url}-${i}`}>
            <span className="lang">{LANG_TEXT[p.language] || p.language}</span>
            <a href={p.url} target="_blank" rel="noopener noreferrer">{p.url}</a>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Quote({ f, label = "Evidence (verbatim from the page)" }) {
  return (
    <>
      <p className="mt-label small">{label}:</p>
      <blockquote className="quote" lang="uz"><mark>{f.evidence_quote}</mark></blockquote>
      <p className="mt">
        <span className="mt-label">{f.evidence_quote_en_label}:</span>{" "}
        {f.evidence_quote_en || "not available"}
      </p>
    </>
  );
}

function PageLink({ url, children }) {
  if (!url) return null;
  return (
    <a className="pagelink" href={url} target="_blank" rel="noopener noreferrer">
      {children || url} ↗
    </a>
  );
}

function Evidence({ f }) {
  if (f.status === "possible_gap") {
    // An absence cannot be quoted: any passage only shows the closest page that was read.
    return (
      <div className="evidence" data-testid="gap-evidence">
        <p className="gap-lead">
          No evidence found on {f.pages_read ?? "no data"} page(s) read. Closest page:
        </p>
        <PageLink url={f.evidence_url} />
        {f.evidence_quote && <Quote f={f} label="Passage from this page (context, not proof)" />}
        {f.context_quote && (
          <>
            <p className="mt-label small">Context from this page (not evidence):</p>
            <blockquote className="quote context" lang="uz"
                        data-testid="context-quote">{f.context_quote}</blockquote>
          </>
        )}
        <p className="muted small">Possible gap for review: a CBU analyst decides.</p>
        {f.reason && <p className="reason">{f.reason}</p>}
        <PagesRead f={f} open />
      </div>
    );
  }
  if (f.status === "not_checkable") {
    return (
      <div className="evidence">
        <p className="nc-lead" data-testid="nc-reason">{reasonHeadline(f.reason)}</p>
        {f.reason && <p className="reason">{f.reason}</p>}
        {f.evidence_quote && <Quote f={f} label="Passage found (not decisive)" />}
        <PageLink url={f.evidence_url} />
        <PagesRead f={f} />
      </div>
    );
  }
  return (
    <div className="evidence">
      {f.evidence_quote ? <Quote f={f} /> : <p className="muted">No verified quote.</p>}
      <PageLink url={f.evidence_url} />
      {f.reason && <p className="reason">{f.reason}</p>}
      <PagesRead f={f} />
    </div>
  );
}

function shortClause(id) {
  return (id || "").replace(/^cbu_reg_3030:/, "Reg. 3030 ").replace(/^law_state_language:/, "State Language Law ");
}

export function FindingsList({ findings, analyst, onDecided, liveRunId }) {
  return (
    <div className="findings" role="table" aria-label="Findings">
      <div className="frow fhead" role="row">
        <div role="columnheader">Bank and requirement</div>
        <div role="columnheader">Status</div>
        <div role="columnheader">Evidence</div>
        <div role="columnheader">Analyst decision</div>
      </div>
      {findings.map((f) => {
        const r = f.requirement;
        return (
          <article className={`frow frow-${f.status}`} role="row" key={f.id} data-testid="finding-row">
            <div role="cell" className="cell-req">
              <span className="bankname">{f.bank_name}</span>
              <h3 className="req-title">
                <span className="req-id">{shortClause(r.clause_id)}</span>{" "}
                {r.short_title || r.text_en || "no data"}
              </h3>
              <details className="req-text">
                <summary>Requirement text</summary>
                <p>{r.text_en || "no data"} <span className="muted small">({r.text_en_label})</span></p>
              </details>
              {r.source_url && (
                <a className="small" href={r.source_url} target="_blank" rel="noopener noreferrer">
                  Clause on lex.uz ↗
                </a>
              )}
              <RunLabel run={f.run} live={liveRunId && f.run && f.run.id === liveRunId} />
            </div>
            <div role="cell" className="cell-status">
              <span className="cell-label">Status</span>
              <StatusBadge status={f.status} />
              <DecidedBy value={f.decided_by} />
            </div>
            <div role="cell">
              <span className="cell-label">Evidence</span>
              <Evidence f={f} />
            </div>
            <div role="cell">
              <span className="cell-label">Analyst decision</span>
              <DecisionBox finding={f} analyst={analyst} onDecided={onDecided} />
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function FindingsSkeleton({ rows = 3 }) {
  return (
    <div className="findings" aria-busy="true" aria-label="Loading findings">
      {Array.from({ length: rows }, (_, i) => (
        <div className="frow skeleton" key={i}>
          <div className="sk sk-line" /><div className="sk sk-chip" />
          <div className="sk sk-block" /><div className="sk sk-block" />
        </div>
      ))}
    </div>
  );
}

export function AnalystField({ analyst, setAnalyst }) {
  return (
    <label className="analyst">
      <span>Analyst name</span>
      <input value={analyst} onChange={(e) => setAnalyst(e.target.value)}
             placeholder="Your name (saved in this browser)" maxLength={100} />
    </label>
  );
}
