import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { AnalystField, FindingsList, Notice, useAnalystName } from "../components/Findings.jsx";

const POLL_MS = 1500;

const CRAWL_TEXT = {
  ok: "Site read",
  blocked: "Blocked by bot protection (not bypassed)",
  unreachable: "Site unreachable",
  robots_disallowed: "robots.txt disallows our crawler",
  needs_browser: "Needs a browser (JavaScript-only site)",
  js_shell_failed: "Browser could not render the site",
  other: "Unexpected response",
};

export default function CheckPage() {
  const [url, setUrl] = useState("");
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [analyst, setAnalyst] = useAnalystName();
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  const poll = async (id) => {
    try {
      const j = await api.job(id);
      setJob(j);
      if (j.status === "queued" || j.status === "running") {
        timer.current = setTimeout(() => poll(id), POLL_MS);
      }
    } catch (e) {
      setError(e);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    clearTimeout(timer.current);
    setError(null);
    setJob(null);
    setSubmitting(true);
    try {
      const { job_id } = await api.startCheck(url.trim());
      await poll(job_id);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  };

  const onDecided = (id, d) =>
    setJob((j) => ({ ...j, findings: j.findings.map((f) => (f.id === id ? { ...f, decision: d } : f)) }));

  const running = job && (job.status === "queued" || job.status === "running");
  const run = job && job.run;

  return (
    <section>
      <h1>Check a website</h1>
      <p className="lead">
        Enter a bank's public https address. The crawler respects robots.txt, waits one second
        between requests and reads a limited number of pages.
      </p>
      <form className="checkform" onSubmit={submit}>
        <label className="sr-only" htmlFor="url">Website URL</label>
        <input id="url" type="url" inputMode="url" required placeholder="https://bank.uz/"
               value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn btn-primary" type="submit" disabled={submitting || running}>
          {running ? "Checking…" : "Check"}
        </button>
      </form>

      {error && (
        <Notice kind={error.status === 429 ? "warn" : "error"}>
          {error.status === 429 ? <strong>Too many checks. </strong> : null}
          {error.message}
        </Notice>
      )}

      {job && (
        <div className="progress" data-testid="job-status">
          <div className={`progress-bar ${running ? "indeterminate" : ""}`}
               aria-hidden="true"><span /></div>
          <p>
            <strong>Status:</strong> {job.status}
            {job.progress && job.progress !== job.status ? ` — ${job.progress}` : ""}
          </p>
          {run && (
            <p className="muted">
              {CRAWL_TEXT[run.crawl_status] || "Crawling"} · {run.pages_read} page(s) read
              {run.fetch_errors && run.fetch_errors.length ? ` · ${run.fetch_errors.length} fetch error(s)` : ""}
              {run.crawl_reason ? ` · ${run.crawl_reason}` : ""}
            </p>
          )}
          {job.status === "error" && <Notice kind="error">The check failed: {job.error}</Notice>}
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
            <>
              <AnalystField analyst={analyst} setAnalyst={setAnalyst} />
              <FindingsList findings={job.findings} analyst={analyst} onDecided={onDecided}
                            liveRunId={run && run.id} />
            </>
          )}
        </div>
      )}
    </section>
  );
}
