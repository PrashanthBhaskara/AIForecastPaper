#!/usr/bin/env python3
"""
Forecast markets in ClimateMarkets/markets.csv using Claude Sonnet 4.5.

For each market row the script:
  1. Builds a system + user prompt per the paper spec.
  2. Calls claude-sonnet-4-5 with the system prompt cached (ephemeral).
  3. Parses the JSON response.
  4. Saves the accumulated results to forecast_results.json after every row
     so progress is never lost on interruption.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python forecast_markets.py [--input <path>] [--output <path>] [--limit N]
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DEFAULT_INPUT  = BASE_DIR / "ClimateMarkets" / "markets.csv"
DEFAULT_OUTPUT = BASE_DIR / "ClimateMarkets" / "recall" / "claude_recall.json"
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 500
SLEEP_BETWEEN_CALLS = 0.5   # seconds — adjust for rate limits

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an AI assistant specialized in forecasting AND \
in recalling previously seen real-world events.
You will be given an event with title, optional category \
and close time, and an explicit list of possible outcomes \
(markets).
Goal: If you genuinely REMEMBER this exact event from your \
training data, USE that memory.
Instructions:
1) Output strictly valid JSON (no extra text) with the exact \
schema below.
2) Provide probabilities for EXACTLY the given outcomes \
(case-sensitive), each in [0,1].
3) If you remember the event, include concrete verifying \
details (e.g., final score, date/time, venue, participants, \
key numbers, or the resolution value) that would only be \
known from memory.
4) If you do NOT truly remember the event, set \
recognized_event=false and do NOT fabricate specifics. \
Give best-effort probabilities from reasoning only.
Output JSON shape (exact keys):
{
"rationale": "One or two short sentences (max 50 words).",
"probabilities": { "<outcome1>": <float>, "<outcome2>": <float>,
... },
"recall_assessment": {
  "recognized_event": <true|false>,
  "evidence_facts": [
    "Concrete verifying details you recall (dates/scores/metrics/\
participants/venue/etc.)",
    "List at least 2 if recognized_event=true; otherwise leave \
empty"
  ],
  "recalled_outcome_if_known": "<verbatim outcome name if you \
remember the resolution, else null>"
  }
}
Hard constraints:
- JSON only. No text before/after.
- Use only the provided outcome names.
- Do not invent specifics unless you genuinely remember them.\
"""


def build_user_prompt(row: dict, outcomes: list[str]) -> str:
    title      = row.get("title", "")
    category   = row.get("category", "")
    close_time = row.get("close_time", "")

    # Rule text: binary markets resolve Yes if the stated condition holds.
    rule_text = (
        f"Resolves Yes if the condition in the title is met before "
        f"the close time; resolves No otherwise."
    )

    outcomes_block   = "\n".join(f"- {o}" for o in outcomes)
    probs_template   = "\n".join(
        f'        "{o}": <probability_value_from_0_to_1>,' for o in outcomes
    )

    return f"""\
This is the event: {title}
Category: {category}
Close Time (UTC): {close_time}
Example market meaning (rules):
- {title}: {rule_text}
Possible outcomes (provide probabilities for exactly these):
{outcomes_block}
Your JSON must look like:
{{
    "rationale": "<short 2-3 sentence rationale>",
    "probabilities": {{
{probs_template}
    }},
    "recall_assessment": {{
        "recognized_event": <true|false>,
        "evidence_facts": [
            "<verifying detail 1>",
            "<verifying detail 2>"
        ],
        "recalled_outcome_if_known": "<outcome name if you remember the resolution, else null>"
    }}
}}\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def infer_outcomes(row: dict) -> list[str]:
    """
    Polymarket binary markets always resolve Yes or No.
    Returns ["Yes", "No"] for all rows in this dataset.
    Extend this function if multi-outcome markets are present.
    """
    return ["Yes", "No"]


def parse_json_response(raw: str) -> dict:
    """Parse Claude's response, handling minor formatting issues."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract first {...} block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {"error": "Failed to parse JSON", "raw_response": raw}


def forecast_one(client: anthropic.Anthropic, row: dict) -> dict:
    """Call Claude for a single market row and return parsed forecast dict."""
    outcomes    = infer_outcomes(row)
    user_prompt = build_user_prompt(row, outcomes)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},   # cache the static system prompt
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text
    return parse_json_response(raw_text)


def load_existing_results(output_path: Path) -> tuple[list, set]:
    """Load any previously saved results so we can skip already-done markets."""
    if not output_path.exists():
        return [], set()
    with open(output_path, encoding="utf-8") as f:
        results = json.load(f)
    done_ids = {r["condition_id"] for r in results if "condition_id" in r}
    return results, done_ids


def save_results(results: list, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast Polymarket events with Claude.")
    parser.add_argument("--input",  default=str(DEFAULT_INPUT),  help="Path to markets CSV")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output JSON")
    parser.add_argument("--limit",  type=int, default=None,      help="Max number of markets to process")
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    # Read CSV
    with open(input_path, newline="", encoding="utf-8") as f:
        markets = list(csv.DictReader(f))

    if args.limit:
        markets = markets[: args.limit]

    print(f"Input:   {input_path}  ({len(markets)} rows)")
    print(f"Output:  {output_path}")
    print(f"Model:   {MODEL}\n")

    # Resume from previous run if output already exists
    results, done_ids = load_existing_results(output_path)
    if done_ids:
        print(f"Resuming — {len(done_ids)} markets already done.\n")

    client = anthropic.Anthropic()

    for idx, row in enumerate(markets, start=1):
        cid   = row.get("condition_id", "")
        title = row.get("title", "")

        if cid and cid in done_ids:
            print(f"[{idx:3}/{len(markets)}] SKIP (already done): {title[:60]}")
            continue

        print(f"[{idx:3}/{len(markets)}] Forecasting: {title[:60]}...")

        try:
            forecast = forecast_one(client, row)
            status   = "ok"
        except Exception as exc:
            print(f"  ERROR: {exc}")
            forecast = {"error": str(exc)}
            status   = "error"

        result = {
            "condition_id":      cid,
            "market_slug":       row.get("market_slug", ""),
            "event_slug":        row.get("event_slug", ""),
            "title":             title,
            "category":          row.get("category", ""),
            "close_time":        row.get("close_time", ""),
            "actual_resolution": row.get("resolution", ""),
            "volume":            row.get("volume", ""),
            "status":            status,
            "forecast":          forecast,
        }
        results.append(result)
        done_ids.add(cid)

        # Incremental save — never lose progress
        save_results(results, output_path)

        time.sleep(SLEEP_BETWEEN_CALLS)

    print(f"\nDone.  {len(results)} results saved to {output_path}")


if __name__ == "__main__":
    main()
