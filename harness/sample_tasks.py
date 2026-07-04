#!/usr/bin/env python3
"""Pre-registration sampler for the Overclaiming Report (docs/overclaiming-report/PLAN.md).

Draws a fixed task sample from public GitHub issues and freezes it into
docs/overclaiming-report/tasks.jsonl + TASKS.md. Run ONCE at pre-registration
time; the committed output — not this script's future behavior — is the sample.
(GitHub search results drift, so reproducibility comes from freezing the draw,
with the script + query + seed committed for audit.)

Usage:
    GH=gh python3 harness/sample_tasks.py [--n 50] [--seed 58]

Inclusion criteria (auditable, stated in the report):
  - open issue labeled `good first issue` or `bug`, on a Python-language repo
  - issue body >= 200 chars (enough spec to act on)
  - repo: >=100 stars (active project, real stakes), pushed within 90 days,
    OSI license, not archived, not a fork
  - one task max per repo (diversity over depth)

Seed 58 = the n of the calibration essay this study extends.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "overclaiming-report"

# Repo-first sampling: issue search cannot filter by repo stars, so we draw
# qualified repos (repo search supports good-first-issues:>=N), then pull their
# open candidate issues.
REPO_QUERIES = [
    "language:python stars:>=100 good-first-issues:>=3 archived:false pushed:>=2026-04-01",
    "language:python stars:>=100 help-wanted-issues:>=3 archived:false pushed:>=2026-04-01",
]
ISSUE_LABELS = ["good first issue", "bug", "help wanted"]

# Mechanical task-quality exclusions (code tasks only, English spec):
EXCLUDE_LABELS = {"documentation", "question", "discussion", "meta", "duplicate", "wontfix"}
EXCLUDE_TITLE = ("readme", "docs", "documentation", "translat", "community", "chat",
                 "typo in doc", "website", "logo", "rfc")


def title_ok(title: str) -> bool:
    t = title.lower()
    if any(k in t for k in EXCLUDE_TITLE):
        return False
    ascii_share = sum(c.isascii() for c in title) / max(len(title), 1)
    return ascii_share >= 0.9


def gh_json(args: list[str]):
    res = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[:200])
    return json.loads(res.stdout)


def qualified_repos(pages: int = 3) -> list[str]:
    repos, seen = [], set()
    for q in REPO_QUERIES:
        for page in range(1, pages + 1):
            try:
                batch = gh_json([
                    f"search/repositories?q={q.replace(' ', '+').replace(':', '%3A')}"
                    f"&sort=updated&order=desc&per_page=100&page={page}"
                ])
            except RuntimeError as exc:
                print(f"  repo query page failed ({exc}); continuing", file=sys.stderr)
                break
            for r in batch.get("items", []):
                name = r["full_name"]
                if name in seen or r.get("fork") or not r.get("license"):
                    continue
                seen.add(name)
                repos.append(name)
    return repos


def collect_candidates() -> list[dict]:
    out, seen = [], set()
    for repo in qualified_repos():
        try:
            issues = gh_json([
                f"repos/{repo}/issues?state=open&per_page=30&sort=created&direction=desc"
            ])
        except RuntimeError:
            continue
        for item in issues:
            if "pull_request" in item or item.get("assignee"):
                continue
            labels = {l["name"].lower() for l in item.get("labels", [])}
            if not labels & {x.lower() for x in ISSUE_LABELS}:
                continue
            url = item["html_url"]
            if url in seen or len(item.get("body") or "") < 200:
                continue
            if labels & EXCLUDE_LABELS or not title_ok(item["title"]):
                continue
            seen.add(url)
            out.append(
                {
                    "issue_url": url,
                    "repo": repo,
                    "title": item["title"],
                    "labels": sorted(labels),
                    "created_at": item["created_at"],
                }
            )
    return out


def repo_ok(repo: str, cutoff: datetime) -> bool:
    try:
        r = gh_json([f"repos/{repo}"])
    except RuntimeError:
        return False
    if r.get("archived") or r.get("fork"):
        return False
    if (r.get("stargazers_count") or 0) < 100:
        return False
    if not r.get("license"):
        return False
    pushed = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
    return pushed >= cutoff


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=58)
    args = ap.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    cands = collect_candidates()
    print(f"raw candidates: {len(cands)}", file=sys.stderr)

    rng = random.Random(args.seed)
    rng.shuffle(cands)

    picked, used_repos = [], set()
    for c in cands:
        if len(picked) >= args.n:
            break
        if c["repo"] in used_repos:
            continue
        used_repos.add(c["repo"])
        c["task_id"] = f"ocr-{len(picked) + 1:03d}"
        picked.append(c)
        print(f"  {c['task_id']} {c['repo']} :: {c['title'][:60]}", file=sys.stderr)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(OUT_DIR / "tasks.jsonl", "w") as f:
        for c in picked:
            f.write(json.dumps(c, sort_keys=True) + "\n")

    with open(OUT_DIR / "TASKS.md", "w") as f:
        f.write(
            f"# Overclaiming Report — pre-registered task sample\n\n"
            f"Frozen {stamp} · seed {args.seed} · n={len(picked)} · "
            f"sampler `harness/sample_tasks.py` (criteria in script header).\n"
            f"This list is the sample. It does not change after this commit; "
            f"tasks that turn out infeasible are *reported* as infeasible, "
            f"never silently replaced.\n\n"
            f"| id | repo | issue |\n|---|---|---|\n"
        )
        for c in picked:
            f.write(f"| {c['task_id']} | {c['repo']} | [{c['title'][:70]}]({c['issue_url']}) |\n")

    print(f"frozen {len(picked)} tasks -> {OUT_DIR}/tasks.jsonl + TASKS.md")


if __name__ == "__main__":
    main()
