"""Consistency of the checks: run all approved checks several times for one bank and
measure how often the answers agree.

    python -m backend.consistency <bank_id> [--runs 2]

Run 1 is a normal check (crawl + checks, normal LLM cache). Runs 2..N replay exactly the
same pages and call the LLM again under a fresh cache namespace, so cached answers are not
reused: the result measures the stability of the LLM answers, not crawl differences.
Agreement per requirement = share of run pairs with the same status (and, separately, the
same evidence quote). The result is stored in SQLite and shown in GET /metrics.
"""

import argparse
import itertools
import json
import sys
import uuid
from dataclasses import replace

from backend import db
from backend.crawl.banks import load_banks
from backend.crawl.crawler import CrawlResult
from backend.models import utcnow
from backend.pipeline import check_site, llm_from_env, sync_requirements_yaml


class _NoStore:
    """Replayed pages are already stored by run 1; never overwrite their crawl links."""

    def get(self, bank_id, url):
        return None

    def put(self, page, links, request_url=None):
        pass


class ReplayCrawler:
    """Returns a previous crawl's pages instead of fetching anything."""

    def __init__(self, crawl: CrawlResult):
        self._crawl = crawl
        self.store = _NoStore()

    def crawl(self, bank_id: str, start_url: str, run_id: str | None = None) -> CrawlResult:
        pages = [p.model_copy(update={"run_id": run_id}) for p in self._crawl.pages]
        return replace(self._crawl, pages=pages, notes=self._crawl.notes + ["replayed pages"])

    def close(self) -> None:
        pass


def pair_agreement(values: list) -> float:
    pairs = list(itertools.combinations(values, 2))
    return sum(a == b for a, b in pairs) / len(pairs) if pairs else 1.0


def compare(findings_per_run: list[list]) -> dict:
    by_req: dict[str, list] = {}
    for findings in findings_per_run:
        for f in findings:
            by_req.setdefault(f.requirement_id, []).append(f)
    per_req = {}
    for req_id, fs in sorted(by_req.items()):
        statuses = [f.status for f in fs]
        quotes = [f.evidence_quote for f in fs]
        per_req[req_id] = {"statuses": statuses,
                           "status_agreement": pair_agreement(statuses),
                           "quote_agreement": pair_agreement(quotes)}
    n = len(per_req)
    return {
        "n_requirements": n,
        "status_agreement": (sum(r["status_agreement"] for r in per_req.values()) / n
                             if n else None),
        "quote_agreement": (sum(r["quote_agreement"] for r in per_req.values()) / n
                            if n else None),
        "per_requirement": per_req,
    }


def run_consistency(bank_id: str, runs: int = 2, db_path=None, progress=print,
                    llm_factory=None, first_crawler=None, banks_path=None) -> dict:
    if runs < 2:
        raise ValueError("--runs must be at least 2")
    banks = load_banks(banks_path) if banks_path else load_banks()
    bank = next((b for b in banks if b.id == bank_id), None)
    if bank is None or not bank.website_url:
        raise ValueError(f"{bank_id}: not in data/banks.yaml or no website_url")
    db.init_db(db_path)
    sync_requirements_yaml(db_path=db_path)
    llm_factory = llm_factory or (lambda: llm_from_env(db_path))
    if llm_factory() is None:
        raise ValueError("LLM not configured: set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL in .env")

    captured: dict = {}
    run_ids = []
    for i in range(runs):
        llm = llm_factory()
        if i > 0:
            llm.cache_namespace = f"consistency-{uuid.uuid4().hex[:8]}"
        progress(f"run {i + 1}/{runs}" + (" (same pages, fresh LLM answers)" if i else ""))
        run = check_site(bank.website_url, bank_id=bank.id, source="consistency", llm=llm,
                         db_path=db_path,
                         crawler=ReplayCrawler(captured["crawl"]) if i else first_crawler,
                         on_crawl=lambda c: captured.setdefault("crawl", c),
                         progress=lambda m: progress(f"  {m}"))
        run_ids.append(run.id)

    with db.connect(db_path) as conn:
        per_run = [db.list_findings(conn, run_id=r) for r in run_ids]
        models = sorted({f"{r['provider']}/{r['model']}" for r in conn.execute(
            f"SELECT DISTINCT provider, model FROM llm_calls WHERE ok = 1 AND cache_hit = 0 "
            f"AND run_id IN ({','.join('?' * len(run_ids))})", run_ids)})
    result = compare(per_run)
    record = {"id": uuid.uuid4().hex[:12], "bank_id": bank.id,
              "created_at": utcnow().isoformat(), "run_ids": run_ids, "models": models,
              **result}
    with db.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO consistency (id, bank_id, created_at, run_ids, n_requirements, "
            "status_agreement, quote_agreement, per_requirement, models) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (record["id"], bank.id, record["created_at"], json.dumps(run_ids),
             result["n_requirements"], result["status_agreement"], result["quote_agreement"],
             json.dumps(result["per_requirement"], ensure_ascii=False), json.dumps(models)))
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the checks repeatedly and measure agreement.")
    ap.add_argument("bank_id")
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args(argv)
    try:
        r = run_consistency(args.bank_id, args.runs,
                            progress=lambda m: print(m, file=sys.stderr))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"\nconsistency for {r['bank_id']} over {len(r['run_ids'])} runs "
          f"(models: {', '.join(r['models']) or 'no API calls'})")
    print(f"{'requirement':40} {'statuses':38} status  quote")
    for req, v in r["per_requirement"].items():
        print(f"{req:40} {' / '.join(v['statuses']):38} {v['status_agreement']:>5.0%}  "
              f"{v['quote_agreement']:>5.0%}")
    if r["status_agreement"] is None:
        print("no data: no approved requirements produced findings")
    else:
        print(f"\nstatus agreement {r['status_agreement']:.0%} and evidence-quote agreement "
              f"{r['quote_agreement']:.0%} on {r['n_requirements']} requirement(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
