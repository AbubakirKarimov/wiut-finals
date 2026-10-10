"""Smoke test of a running ComplianceRadar deployment (Docker, Render or local uvicorn).

    python3 scripts/smoke_hosted.py <base_url> [--wait SECONDS]

Checks: GET /health is {"status": "ok"}; GET /findings returns a non-empty list; GET /metrics
returns the metrics object; GET / returns the HTML app shell (<div id="root">). Standard
library only. --wait (default 120) retries /health while a sleeping free-plan service starts.
Exit code 0 when every check passes.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def get(base: str, path: str, timeout: float = 30) -> tuple[int, str, float]:
    t = time.perf_counter()
    req = urllib.request.Request(base.rstrip("/") + path,
                                 headers={"User-Agent": "ComplianceRadar-smoke/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), time.perf_counter() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), time.perf_counter() - t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--wait", type=float, default=120)
    args = ap.parse_args()
    base, results = args.base_url, []

    deadline = time.monotonic() + args.wait
    while True:  # cold start: Render's free plan sleeps after inactivity
        try:
            status, body, secs = get(base, "/health", timeout=10)
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if time.monotonic() > deadline:
                print(f"FAIL /health: not reachable within {args.wait:.0f} s ({e})")
                return 1
            time.sleep(3)
    results.append(("/health", status == 200 and json.loads(body) == {"status": "ok"},
                    f"HTTP {status} in {secs:.2f} s: {body[:60]}"))

    status, body, secs = get(base, "/findings")
    try:
        data = json.loads(body)
        sources = sorted({(f.get("run") or {}).get("source") or "?" for f in data})
        ok = status == 200 and isinstance(data, list) and len(data) > 0
        detail = f"HTTP {status} in {secs:.2f} s: {len(data)} findings (run sources: {sources})"
    except ValueError:
        ok, detail = False, f"HTTP {status}: not JSON"
    results.append(("/findings", ok, detail))

    status, body, secs = get(base, "/metrics")
    try:
        m = json.loads(body)
        ok = status == 200 and "checks_completed" in m and "decided_by" in m
        detail = (f"HTTP {status} in {secs:.2f} s: checks_completed={m.get('checks_completed')}, "
                  f"team_review={(m.get('team_review') or {}).get('label')}")
    except ValueError:
        ok, detail = False, f"HTTP {status}: not JSON"
    results.append(("/metrics", ok, detail))

    status, body, secs = get(base, "/")
    has_root = '<div id="root">' in body
    results.append(("/", status == 200 and has_root,
                    f"HTTP {status} in {secs:.2f} s: app root {'found' if has_root else 'MISSING'}"))

    for path, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {path:<10} {detail}")
    passed = all(ok for _, ok, _ in results)
    print("smoke test:", "PASSED" if passed else "FAILED", f"({base})")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
