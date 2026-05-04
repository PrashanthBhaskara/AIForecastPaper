"""
Grade recall files and add recall_score to each item's forecast.recall_assessment.

recall_score:
  0.0  — recalled_outcome_if_known != actual_resolution (wrong answer)
  0.5  — correct answer but reasoning has factual errors
  1.0  — correct answer, reasoning is factually clean
  null — recalled_outcome_if_known is null/missing (not graded)

Usage:
  python grade_recall.py path/to/file.json [path/to/other.json ...]
  python grade_recall.py Research/ClimateMarkets/recall/*.json
"""

import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

MODEL = "claude-haiku-4-5"
MAX_WORKERS = 4
API_KEY =  "ENTER" # Set your ANTHROPIC_API_KEY environment variable instead of hardcoding here

GRADER_SYSTEM = GRADER_SYSTEM = """You are a meticulous fact-checker. You will be given:
1. A prediction market question and its actual resolution
2. An LLM's reasoning explaining why it predicted the (correct) outcome

Your job: identify factual errors in the reasoning. Check concrete claims —
dates, names, years, ceremony numbers, chart positions, box-office figures,
who beat whom, song/album/film titles.

CRITICAL RULE ON FLAGGING: Only flag a claim as wrong if you are highly
confident it is wrong. A confidently asserted "correction" that turns out
to be wrong is worse than missing an error. If you are pattern-matching
from memory and not certain, do NOT flag it. When in doubt, default to
CORRECT. The actual_resolution is your strongest anchor — claims consistent
with it should not be flagged unless clearly contradicted by other widely
known facts.

Do NOT penalize:
- Hedging language ("I recall", "I think", "uncertain")
- Probabilistic estimates
- Missing information (only flag stated facts that are wrong)
- Minor rounding or approximations within ~10% (e.g. "$80M" vs "$80.5M",
  "$35M" vs "$35.4M")
- Slight phrasing differences in titles, names, or roles

Flag as errors only when clearly wrong:
- Wrong dates or years (off by months/years, not days)
- Wrong winners or who-beat-whom claims
- Box-office or chart figures off by more than ~10%
- Misattributed songs, albums, or films to the wrong artist
- Internally inconsistent claims within the reasoning itself

Respond in this exact format:

VERDICT: CORRECT
or
VERDICT: ERRORS_FOUND

ERRORS:
- <error 1, one line, with the correct fact>
- <error 2, one line, with the correct fact>
(omit ERRORS section if VERDICT is CORRECT)
"""

GRADER_USER_TEMPLATE = """Question: {title}
Actual resolution: {actual_resolution}
Close time: {close_time}

LLM's reasoning:
\"\"\"
{rationale}
\"\"\"

Evidence facts the LLM cited:
{evidence_facts}

Fact-check the reasoning and evidence. Are there any factual errors?"""


def normalize(x):
    if x is None:
        return None
    return str(x).strip().lower()


def answer_matches(recalled, actual):
    r, a = normalize(recalled), normalize(actual)
    if r is None or a is None:
        return None
    return r == a


def parse_verdict(text):
    m = re.search(r"VERDICT:\s*(CORRECT|ERRORS_FOUND)", text, re.I)
    verdict = m.group(1).upper() if m else "UNKNOWN"
    errors = []
    if verdict == "ERRORS_FOUND":
        parts = re.split(r"ERRORS:", text, flags=re.I, maxsplit=1)
        if len(parts) == 2:
            for line in parts[1].splitlines():
                line = line.strip()
                if line.startswith(("-", "*", "•")):
                    errors.append(line.lstrip("-*• ").strip())
    return verdict, errors


def grade_reasoning(client, item, max_retries=3):
    forecast = item.get("forecast", {})
    recall = forecast.get("recall_assessment", {}) or {}
    evidence = recall.get("evidence_facts") or []
    evidence_str = "\n".join(f"- {f}" for f in evidence) if evidence else "(none provided)"

    user_msg = GRADER_USER_TEMPLATE.format(
        title=item.get("title", ""),
        actual_resolution=item.get("actual_resolution", ""),
        close_time=item.get("close_time", ""),
        rationale=forecast.get("rationale", ""),
        evidence_facts=evidence_str,
    )

    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=GRADER_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 4,
                }],
            )
            # Collect all text blocks; the verdict is in the last text block
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
            return parse_verdict(text)
        except (anthropic.RateLimitError, anthropic.APIStatusError):
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    return "UNKNOWN", []


def compute_score(client, item):
    """Return (score, verdict, errors) for one item."""
    forecast = item.get("forecast") or {}
    recall = forecast.get("recall_assessment") or {}
    recalled = recall.get("recalled_outcome_if_known")
    actual = item.get("actual_resolution")

    match = answer_matches(recalled, actual)

    if match is None:
        return None, None, []
    if not match:
        return 0.0, None, []

    verdict, errors = grade_reasoning(client, item)
    if verdict == "CORRECT":
        return 1.0, verdict, errors
    if verdict == "ERRORS_FOUND":
        return 0.5, verdict, errors
    return None, verdict, errors


def process_file(client, path: Path, workers: int):
    items = json.loads(path.read_text())
    total = len(items)
    print(f"\n=== {path} ({total} items) ===")

    VALID_SCORES = {0, 0.5, 1, 0.0, 1.0}

    # Pre-populate already-graded items and filter pending
    results = [None] * total
    pending = []
    skipped_done = 0
    skipped_wrong = 0
    for i, item in enumerate(items):
        ra = (item.get("forecast") or {}).get("recall_assessment") or {}
        if ra.get("recall_score") in VALID_SCORES:
            results[i] = (ra["recall_score"], ra.get("grader_verdict"), ra.get("grader_errors") or [])
            skipped_done += 1
            continue
        recalled = ra.get("recalled_outcome_if_known")
        actual = item.get("actual_resolution")
        if normalize(recalled) is not None and normalize(recalled) != normalize(actual):
            skipped_wrong += 1
            continue
        pending.append((i, item))

    print(f"  {skipped_done} already graded, {skipped_wrong} wrong-answer skipped, {len(pending)} to process")

    def grade(idx_item):
        idx, item = idx_item
        score, verdict, errors = compute_score(client, item)
        return idx, score, verdict, errors

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(grade, (i, item)): i for i, item in pending}
        for fut in as_completed(futures):
            try:
                idx, score, verdict, errors = fut.result()
            except Exception as e:
                idx = futures[fut]
                score, verdict, errors = None, None, []
                print(f"  [{idx}] ERROR: {e}")
            results[idx] = (score, verdict, errors)
            done += 1
            item = items[idx]
            title = item.get("title", "")[:60]
            print(f"  [{done}/{total}] score={score}  {title}")

    # Inject recall_score (and grader metadata) back into each item
    for i, item in enumerate(items):
        score, verdict, errors = results[i]
        ra = item.setdefault("forecast", {}).setdefault("recall_assessment", {})
        ra["recall_score"] = score
        if verdict is not None:
            ra["grader_verdict"] = verdict
        if errors:
            ra["grader_errors"] = errors

    path.write_text(json.dumps(items, indent=2))
    print(f"  -> written back to {path}")

    # Per-file summary
    scored = [(s, v, e) for s, v, e in results if s is not None]
    if scored:
        n = len(scored)
        mean = sum(s for s, _, _ in scored) / n
        c0 = sum(1 for s, _, _ in scored if s == 0.0)
        c5 = sum(1 for s, _, _ in scored if s == 0.5)
        c1 = sum(1 for s, _, _ in scored if s == 1.0)
        print(f"  Summary: n={n} mean={mean:.3f}  1.0={c1} 0.5={c5} 0.0={c0} skipped={total-n}")


def main():
    parser = argparse.ArgumentParser(description="Grade recall JSON files and add recall_score in-place.")
    parser.add_argument("files", nargs="+", type=Path, help="One or more recall JSON files")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="Parallel API threads per file")
    args = parser.parse_args()

    api_key = API_KEY or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY environment variable.")

    client = anthropic.Anthropic(api_key=api_key)

    all_scores = []
    for path in args.files:
        if not path.exists():
            print(f"WARNING: {path} not found, skipping.")
            continue
        process_file(client, path, args.workers)

    print("\nDone.")


if __name__ == "__main__":
    main()