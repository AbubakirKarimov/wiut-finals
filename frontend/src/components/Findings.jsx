import { useState } from "react";
import { api, formatTime } from "../api.js";

const STATUS_TEXT = {
  ok: "OK",
  possible_gap: "Possible gap for review",
  not_checkable: "Not checkable",
};

export function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_TEXT[status] || status}</span>;
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

function UrlsRead({ f, open }) {
  if (f.pages_read == null) return null;
  return (
    <details className="urls" open={open}>
      <summary>{f.pages_read} page(s) read</summary>
      <ul>
        {f.urls_read.map((u) => (
          <li key={u}><a href={u} target="_blank" rel="noopener noreferrer">{u}</a></li>
        ))}
      </ul>
    </details>
  );
}

function Quote({ f }) {
  return (
    <>
      <blockquote className="quote" lang="uz">{f.evidence_quote}</blockquote>
      <p className="mt">
        <span className="mt-label">{f.evidence_quote_en_label}:</span>{" "}
        {f.evidence_quote_en || "not available"}
      </p>
    </>
  );
}

function PageLink({ url, children = "Open bank page ↗" }) {
  if (!url) return null;
  return <a className="pagelink" href={url} target="_blank" rel="noopener noreferrer">{children}</a>;
}

function Evidence({ f }) {
  if (f.status === "possible_gap") {
    // An absence cannot be quoted: the quote only shows the closest page that was read.
    return (
      <div className="evidence" data-testid="gap-evidence">
        <p className="gap-lead">
          No evidence found on {f.pages_read ?? "no data"} page(s) read. Closest page:
        </p>
        <PageLink url={f.evidence_url}>{f.evidence_url}</PageLink>
        {f.evidence_quote && <Quote f={f} />}
        <p className="muted small">
          The passage above is context from the closest page, not proof. Possible gap for
          review: a CBU analyst decides.
        </p>
        {f.reason && <p className="reason">{f.reason}</p>}
        <UrlsRead f={f} open />
      </div>
    );
  }
  return (
    <div className="evidence">
      {f.evidence_quote ? <Quote f={f} /> : <p className="muted">No verified quote.</p>}
      <PageLink url={f.evidence_url} />
      {f.reason && <p className="reason">{f.reason}</p>}
      <UrlsRead f={f} />
    </div>
  );
}

export function FindingsList({ findings, analyst, onDecided, liveRunId }) {
  return (
    <div className="findings" role="table" aria-label="Findings">
      <div className="frow fhead" role="row">
        <div role="columnheader">Bank</div>
        <div role="columnheader">Requirement</div>
        <div role="columnheader">Status</div>
        <div role="columnheader">Evidence</div>
        <div role="columnheader">Analyst decision</div>
      </div>
      {findings.map((f) => (
        <div className="frow" role="row" key={f.id} data-testid="finding-row">
          <div role="cell" className="cell-bank">
            <span className="cell-label">Bank</span>
            <strong>{f.bank_name}</strong>
            <RunLabel run={f.run} live={liveRunId && f.run && f.run.id === liveRunId} />
          </div>
          <div role="cell">
            <span className="cell-label">Requirement</span>
            <p className="req">{f.requirement.text_en || "no data"}</p>
            <p className="muted small">
              {f.requirement.text_en_label} ·{" "}
              {f.requirement.source_url ? (
                <a href={f.requirement.source_url} target="_blank" rel="noopener noreferrer">
                  {f.requirement.clause_id} on lex.uz ↗
                </a>
              ) : f.requirement.clause_id}
              {" · "}{f.requirement.check_type}
            </p>
          </div>
          <div role="cell">
            <span className="cell-label">Status</span>
            <StatusBadge status={f.status} />
          </div>
          <div role="cell">
            <span className="cell-label">Evidence</span>
            <Evidence f={f} />
          </div>
          <div role="cell">
            <span className="cell-label">Analyst decision</span>
            <DecisionBox finding={f} analyst={analyst} onDecided={onDecided} />
          </div>
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
