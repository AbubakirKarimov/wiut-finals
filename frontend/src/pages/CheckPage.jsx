import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import {
  AnalystField, FindingsList, Notice, reasonHeadline, useAnalystName,
} from "../components/Findings.jsx";

const POLL_MS = 1500;

// Human message per crawl outcome (the technical reason is shown below it).
const CRAWL_TEXT = {
  blocked: "The site blocked our crawler. Bot protection is never bypassed, so nothing could be checked.",
  unreachable: "The site could not be reached (DNS, timeout or connection error).",
  robots_disallowed: "The site's robots.txt does not allow our crawler, so it was not read.",
  js_shell_failed: "This site renders its content with JavaScript and could not be rendered (browser or Jina Reader). Nothing was judged.",
  other: "The site returned an unexpected response.",
};

export function validateUrl(raw) {
  const v = raw.trim();
  if (!v) return "Enter a website address.";
  let u;
  try {
    u = new URL(v);
  } catch {
    return "This is not a valid address. Example: https://bank.uz/";
  }
  // The server decides what is allowed (public https only, unless configured otherwise).
  if (u.protocol !== "https:" && u.protocol !== "http:") return "The address must start with https://";
  if (!u.hostname) return "Enter a domain name, for example https://bank.uz/";
  return "";
}

// Stage of a running job, from its real progress events.
export function stageOf(progress, prev) {
  const p = progress || "";
  const pages = p.match(/page (\d+)\/(\d+)/);
  const checks = p.match(/check (\d+)\/(\d+)/);
  const crawlDone = p.match(/crawl \w+: (\d+) page/);
  const next = { ...prev };
  if (pages) Object.assign(next, { stage: 1, pages: +pages[1], pagesMax: +pages[2] });
  else if (crawlDone) Object.assign(next, { stage: 2, pages: +crawlDone[1] });
  else if (/running \d+ approved/.test(p)) {
    const n = p.match(/running (\d+)/);
    Object.assign(next, { stage: 2, checks: 0, checksMax: +n[1] });
  } else if (checks) Object.assign(next, { stage: 2, checks: +checks[1], checksMax: +checks[2] });
  else if (/home page/.test(p) && next.stage === undefined) next.stage = 0;
  return next;
}

// The hosted demo has no browser: a JavaScript-only site ends with nothing judged.
export function isJsOnly(job) {
  return Boolean(job && job.status === "done" && job.run && job.run.crawl_status === "needs_browser"
    && job.findings.every((f) => f.status === "not_checkable"));
}

function JsOnlyNotice({ job }) {
  return (
    <Notice kind="warn">
      <span data-testid="js-only-message">
        This site renders its content with JavaScript, which the hosted demo cannot read
        (no browser here, and the optional Jina Reader fallback is off). Nothing was judged.
        {job.precomputed_findings > 0 && (
          <> Pre-computed results for this bank (made with a browser) are on
            the <a href="#/findings">Findings tab</a>.</>
        )}
      </span>
      {job.run.crawl_reason && (
        <details className="tech">
          <summary>Details</summary>
          <p>{job.run.crawl_reason}</p>
        </details>
      )}
    </Notice>
  );
}

function Stepper({ job, st, elapsed }) {
  const done = job.status === "done";
  const jsOnly = isJsOnly(job);
  // When finished, show the final counts from the run, not the last polled event.
  const pages = done && job.run ? job.run.pages_read : st.pages;
  const checks = done ? job.findings.length : st.checks;
  const checksMax = done ? job.findings.length : st.checksMax;
  const steps = [
    { label: "Crawling site", detail: st.stage === 0 ? "fetching home page" : "" },
    { label: "Reading pages", detail: pages != null ? (done ? `${pages} read` : `${pages}/${st.pagesMax || "?"}`) : "" },
    { label: "Running checks", detail: checksMax != null ? `${checks}/${checksMax}` : "" },
    jsOnly ? { label: "Not available on this hosted demo", detail: "", warn: true } : { label: "Done", detail: "" },
  ];
  const current = done ? 4 : st.stage ?? 0;
  return (
    <ol className="stepper" aria-label="Check progress">
      {steps.map((s, i) => {
        const state = s.warn ? "warn" : i < current || done ? "done" : i === current ? "active" : "todo";
        return (
          <li key={s.label} className={`step step-${state}`} aria-current={state === "active" ? "step" : undefined}>
            <span className="step-dot" aria-hidden="true">{state === "done" ? "✓" : state === "warn" ? "!" : i + 1}</span>
            <span className="step-label">{s.label}</span>
            {s.detail && <span className="step-detail">{s.detail}</span>}
          </li>
        );
      })}
      <li className="elapsed" data-testid="elapsed">Elapsed {elapsed}s</li>
    </ol>
  );
}

function HowItWorks() {
  const steps = ["Law clause", "Check", "Evidence", "Analyst decision", "Audit log"];
  return (
    <section className="how" aria-label="How it works">
      <ol className="how-steps">
        {steps.map((s, i) => (
          <li key={s}><span className="how-n">{i + 1}</span>{s}</li>
        ))}
      </ol>
      <p className="muted small">
        Production design: designed to run on a local model inside the regulator&rsquo;s perimeter
        (not yet measured in this prototype).
      </p>
    </section>
  );
}

export default function CheckPage() {
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [st, setSt] = useState({});
  const [started, setStarted] = useState(null);
  const [now, setNow] = useState(Date.now());
  const [examples, setExamples] = useState([]);
  const [analyst, setAnalyst] = useAnalystName();
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    api.banks()
      // Only sites measured readable without a browser (data/hosted_examples.json).
      .then((bs) => setExamples(bs.filter((b) => b.website_url && b.works_on_hosted).slice(0, 3).map((b) => b.website_url)))
      .catch(() => setExamples([]));
  }, []);

  const running = job && (job.status === "queued" || job.status === "running");
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);

  const poll = async (id) => {
    try {
      const j = await api.job(id);
      setJob(j);
      setSt((prev) => stageOf(j.progress, prev));
      setNow(Date.now());
      if (j.status === "queued" || j.status === "running") {
        timer.current = setTimeout(() => poll(id), POLL_MS);
      }
    } catch (e) {
      setError(e);
    }
  };

  const start = async (target) => {
    const msg = validateUrl(target);
    setUrlError(msg);
    if (msg) return;
    clearTimeout(timer.current);
    setError(null);
    setJob(null);
    setSt({});
    setCancelling(false);
    setSubmitting(true);
    setStarted(Date.now());
    try {
      const { job_id } = await api.startCheck(target.trim());
      await poll(job_id);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const submit = (e) => {
    e.preventDefault();
    start(url);
  };

  const cancel = async () => {
    if (!job) return;
    setCancelling(true);
    try {
      await api.cancelJob(job.id);
    } catch (e) {
      setError(e);
      setCancelling(false);
    }
  };

  const onDecided = (id, d) =>
    setJob((j) => ({ ...j, findings: j.findings.map((f) => (f.id === id ? { ...f, decision: d } : f)) }));

  const run = job && job.run;
  const jsOnly = isJsOnly(job);
  const elapsed = started ? Math.max(0, Math.round((now - started) / 1000)) : 0;
  const quotaHit = job && job.status === "done"
    ? job.findings.filter((f) => /LLM timeout|rate limit|quota/i.test(f.reason || "")).length : 0;
  const retry = <button type="button" className="btn" onClick={() => start(url)}>Retry</button>;

  return (
    <section>
      <h1>Check a website</h1>
      <p className="lead">
        Enter any public https address, a bank in the list or not. The crawler respects
        robots.txt, waits one second between requests and reads at most 15 pages.
      </p>
      <HowItWorks />
      <form className="checkform" onSubmit={submit} noValidate>
        <label className="sr-only" htmlFor="url">Website URL</label>
        <input id="url" type="url" inputMode="url" placeholder="https://bank.uz/"
               aria-invalid={urlError ? "true" : "false"} aria-describedby="url-hint"
               value={url} onChange={(e) => { setUrl(e.target.value); setUrlError(""); }} />
        <button className="btn btn-primary" type="submit" disabled={submitting || running}>
          {running ? "Checking…" : "Check"}
        </button>
      </form>
      <p id="url-hint" className={urlError ? "field-error" : "muted small"} role={urlError ? "alert" : undefined}>
        {urlError || "Must start with https://"}
      </p>
      {examples.length > 0 && (
        <p className="examples small">
          Examples:{" "}
          {examples.map((x) => (
            <button key={x} type="button" className="chip chip-small" onClick={() => { setUrl(x); setUrlError(""); }}>
              {x.replace(/^https:\/\//, "").replace(/\/$/, "")}
            </button>
          ))}
        </p>
      )}

      {error && (
        <Notice kind={error.status === 429 ? "warn" : "error"}>
          {error.status === 429 ? <strong>Too many checks. </strong> : null}
          {error.status === 422 ? <strong>Address not accepted. </strong> : null}
          {error.message} {error.status !== 422 && retry}
        </Notice>
      )}

      {job && (
        <div className="progress" data-testid="job-status">
          <Stepper job={job} st={st} elapsed={elapsed} />
          <p className="small">
            <strong>Status:</strong>{" "}
            {jsOnly ? <span data-testid="status-label">finished, nothing judged</span> : (
              <>
                {job.status}
                {job.progress && job.progress !== job.status ? ` — ${job.progress}` : ""}
              </>
            )}
          </p>
          {running && (
            <button type="button" className="btn" onClick={cancel} disabled={cancelling}>
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
          {job.status === "cancelled" && <Notice kind="warn">Check cancelled. Nothing was saved as a result. {retry}</Notice>}
          {job.status === "error" && (
            <Notice kind="error">
              The check failed{/server restarted/.test(job.error || "") ? " because the server restarted" : ""}.{" "}
              <span className="small">({job.error})</span> {retry}
            </Notice>
          )}
          {jsOnly && <JsOnlyNotice job={job} />}
          {run && run.crawl_status === "ok" && /Jina Reader/.test(run.crawl_reason || "") && (
            <Notice>
              <span data-testid="jina-note">
                Some pages were rendered by Jina Reader, an external service: only the public
                page address was sent to it. Quotes are verified against the text it returned.
              </span>
            </Notice>
          )}
          {!jsOnly && run && run.crawl_status && run.crawl_status !== "ok" && (
            <Notice kind="error">
              {CRAWL_TEXT[run.crawl_status] || "The site could not be read."}{" "}
              {run.crawl_reason && <span className="small">({run.crawl_reason})</span>} {retry}
            </Notice>
          )}
          {quotaHit > 0 && (
            <Notice kind="warn">
              {reasonHeadline("LLM timeout")}: {quotaHit} check(s) could not run. {retry}
            </Notice>
          )}
        </div>
      )}

      {job && job.status === "done" && (
        <div className="results" data-testid="results">
          <h2>Results</h2>
          {job.approved_requirements === 0 ? (
            <Notice kind="warn">
              No requirements are approved yet, so nothing was checked. Approve requirements with
              <code> python -m backend.requirements.approve</code> (see README).
            </Notice>
          ) : job.findings.length === 0 ? (
            <Notice>No findings were produced for this run.</Notice>
          ) : (
            jsOnly ? (
              // Every card would repeat the message above: keep them out of the way.
              <details className="tech" data-testid="js-only-checks">
                <summary>{job.findings.length} check(s), all not checkable</summary>
                <FindingsList findings={job.findings} analyst={analyst} onDecided={onDecided}
                              liveRunId={run && run.id} />
              </details>
            ) : (
              <>
                <AnalystField analyst={analyst} setAnalyst={setAnalyst} />
                <FindingsList findings={job.findings} analyst={analyst} onDecided={onDecided}
                              liveRunId={run && run.id} />
              </>
            )
          )}
        </div>
      )}
    </section>
  );
}
