#!/usr/bin/env python3
"""
Forecast resolved Polymarket markets with ChatGPT via the OpenAI Responses API.

This mirrors ``Research/claude_recall.py`` closely so Claude and ChatGPT
outputs stay comparable:
  1. Read market rows from a CSV.
  2. Build a recall-oriented prompt per row.
  3. Request structured JSON output from ChatGPT.
  4. Save results after every row so interrupted runs can resume.

The script is inert until run manually. It does not make any network calls on
import, and ``--dry-run`` avoids API access entirely.

Typical usage once credentials are configured:
    pip install openai
    export OPENAI_API_KEY=sk-...
    python Research/chatgpt_recall.py --input Research/curated_events.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).parent
DEFAULT_INPUT = BASE_DIR / "ClimateMarkets" / "markets.csv"
DEFAULT_OUTPUT = BASE_DIR / "ClimateMarkets" / "recall" / "chatgpt_recall.json"
DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-2024-08-06")
DEFAULT_MAX_OUTPUT_TOKENS = 500
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SLEEP_BETWEEN_CALLS = 0.5


SYSTEM_PROMPT = """\
You are an AI assistant specialized in forecasting AND in recalling previously
seen real-world events.
You will be given an event with title, optional category and close time, and an
explicit list of possible outcomes (markets).
Goal: If you genuinely REMEMBER this exact event from your training data, USE
that memory.
Instructions:
1) Output strictly valid JSON with the required schema.
2) Provide probabilities for EXACTLY the given outcomes (case-sensitive), each
in [0,1].
3) If you remember the event, include concrete verifying details (e.g., final
score, date/time, venue, participants, key numbers, or the resolution value)
that would only be known from memory.
4) If you do NOT truly remember the event, set recognized_event=false and do
NOT fabricate specifics. Give best-effort probabilities from reasoning only.
Hard constraints:
- JSON only.
- Use only the provided outcome names.
- Do not invent specifics unless you genuinely remember them.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forecast Polymarket events with ChatGPT.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to input CSV.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of markets to process.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"OpenAI model to use. Default: {DEFAULT_MODEL}")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help=f"Max tokens per response. Default: {DEFAULT_MAX_OUTPUT_TOKENS}",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature. Default: {DEFAULT_TEMPERATURE}",
    )
    parser.add_argument(
        "--sleep-between-calls",
        type=float,
        default=DEFAULT_SLEEP_BETWEEN_CALLS,
        help=f"Seconds to sleep between API calls. Default: {DEFAULT_SLEEP_BETWEEN_CALLS}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and show planned work without calling the OpenAI API.",
    )
    return parser


def build_user_prompt(row: dict[str, str], outcomes: list[str]) -> str:
    title = row.get("title", "")
    category = row.get("category") or row.get("domain", "")
    close_time = row.get("close_time") or row.get("close_date", "")

    rule_text = (
        f"Resolves Yes if the condition in the title is met before "
        f"the close time; resolves No otherwise."
    )

    outcomes_block = "\n".join(f"- {outcome}" for outcome in outcomes)

    return f"""\
This is the event: {title}
Category: {category}
Close Time (UTC): {close_time}
Example market meaning (rules):
- {title}: {rule_text}
Possible outcomes (provide probabilities for exactly these):
{outcomes_block}
"""


def parse_json_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {"error": "Failed to parse JSON", "raw_response": raw}


def parse_outcomes_field(raw_value: str) -> list[str]:
    if not raw_value.strip():
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        outcomes = [str(item).strip() for item in parsed if str(item).strip()]
        return outcomes

    separators = ("|", ";", ",")
    for separator in separators:
        if separator in raw_value:
            return [piece.strip() for piece in raw_value.split(separator) if piece.strip()]
    return [raw_value.strip()]


def infer_outcomes(row: dict[str, str]) -> list[str]:
    for field_name in ("outcomes", "market_outcomes", "tokens"):
        raw_value = row.get(field_name, "")
        outcomes = parse_outcomes_field(raw_value)
        if outcomes:
            return outcomes
    return ["Yes", "No"]


def response_schema(outcomes: list[str]) -> dict[str, Any]:
    probability_properties = {
        outcome: {
            "type": "number",
            "description": f"Probability assigned to outcome {outcome!r}.",
        }
        for outcome in outcomes
    }
    return {
        "type": "object",
        "properties": {
            "rationale": {
                "type": "string",
                "description": "One or two short sentences, max 50 words.",
            },
            "probabilities": {
                "type": "object",
                "properties": probability_properties,
                "required": list(outcomes),
                "additionalProperties": False,
            },
            "recall_assessment": {
                "type": "object",
                "properties": {
                    "recognized_event": {"type": "boolean"},
                    "evidence_facts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Concrete verifying details recalled from memory. "
                            "Leave empty if the event is not recognized."
                        ),
                    },
                    "recalled_outcome_if_known": {
                        "type": ["string", "null"],
                        "enum": list(outcomes),
                        "description": "Verbatim outcome name if the resolution is remembered.",
                    },
                },
                "required": [
                    "recognized_event",
                    "evidence_facts",
                    "recalled_outcome_if_known",
                ],
                "additionalProperties": False,
            },
        },
        "required": ["rationale", "probabilities", "recall_assessment"],
        "additionalProperties": False,
    }


def validate_forecast_payload(payload: dict[str, Any], outcomes: list[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("response payload is not a JSON object")

    if "error" in payload:
        return payload

    rationale = payload.get("rationale")
    probabilities = payload.get("probabilities")
    recall_assessment = payload.get("recall_assessment")

    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("missing or invalid rationale")
    if not isinstance(probabilities, dict):
        raise ValueError("missing or invalid probabilities object")
    if set(probabilities) != set(outcomes):
        raise ValueError(
            f"probability keys {sorted(probabilities)} do not match expected outcomes {sorted(outcomes)}"
        )
    normalized_probabilities: dict[str, float] = {}
    for outcome in outcomes:
        value = probabilities.get(outcome)
        if not isinstance(value, (int, float)):
            raise ValueError(f"probability for {outcome!r} is not numeric")
        numeric = float(value)
        if numeric < 0.0 or numeric > 1.0:
            raise ValueError(f"probability for {outcome!r} is outside [0,1]")
        normalized_probabilities[outcome] = numeric

    if not isinstance(recall_assessment, dict):
        raise ValueError("missing or invalid recall_assessment")
    recognized_event = recall_assessment.get("recognized_event")
    evidence_facts = recall_assessment.get("evidence_facts")
    recalled_outcome = recall_assessment.get("recalled_outcome_if_known")

    if not isinstance(recognized_event, bool):
        raise ValueError("recognized_event must be boolean")
    if not isinstance(evidence_facts, list) or any(not isinstance(item, str) for item in evidence_facts):
        raise ValueError("evidence_facts must be a list of strings")
    if recalled_outcome is not None and recalled_outcome not in outcomes:
        raise ValueError("recalled_outcome_if_known must be null or one of the provided outcomes")

    return {
        "rationale": rationale.strip(),
        "probabilities": normalized_probabilities,
        "recall_assessment": {
            "recognized_event": recognized_event,
            "evidence_facts": [item.strip() for item in evidence_facts if item.strip()],
            "recalled_outcome_if_known": recalled_outcome,
        },
    }


def load_existing_results(output_path: Path) -> tuple[list[dict[str, Any]], set[str]]:
    if not output_path.exists():
        return [], set()
    with output_path.open(encoding="utf-8") as handle:
        results = json.load(handle)
    done_ids = {row["condition_id"] for row in results if isinstance(row, dict) and row.get("condition_id")}
    return results, done_ids


def save_results(results: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, ensure_ascii=False)


def require_openai_client_class():
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "OpenAI SDK not installed. Install it with `pip install openai` before running this script."
        ) from exc
    return OpenAI


def response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    pieces: list[str] = []
    output_items = getattr(response, "output", None) or []
    for item in output_items:
        item_type = getattr(item, "type", None)
        if item_type != "message":
            continue
        for content_item in getattr(item, "content", None) or []:
            if getattr(content_item, "type", None) != "output_text":
                continue
            text = getattr(content_item, "text", None)
            if isinstance(text, str) and text:
                pieces.append(text)
    return "".join(pieces)


def forecast_one(client: Any, row: dict[str, str], model: str, max_output_tokens: int, temperature: float) -> dict[str, Any]:
    outcomes = infer_outcomes(row)
    user_prompt = build_user_prompt(row, outcomes)

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=[{"role": "user", "content": user_prompt}],
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        text={
            "format": {
                "type": "json_schema",
                "name": "market_recall_forecast",
                "strict": True,
                "schema": response_schema(outcomes),
            }
        },
    )

    raw_text = response_output_text(response)
    parsed = parse_json_response(raw_text)
    return validate_forecast_payload(parsed, outcomes)


def validate_args(args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be zero or positive")
    if args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be positive")
    if args.sleep_between_calls < 0:
        raise SystemExit("--sleep-between-calls must be zero or positive")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        raise SystemExit(f"Input CSV not found: {input_path}")

    with input_path.open(newline="", encoding="utf-8") as handle:
        markets = list(csv.DictReader(handle))

    if args.limit is not None:
        markets = markets[: args.limit]

    print(f"Input:   {input_path}  ({len(markets)} rows)")
    print(f"Output:  {output_path}")
    print(f"Model:   {args.model}")
    print(f"Mode:    {'dry-run' if args.dry_run else 'live'}\n")

    results, done_ids = load_existing_results(output_path)
    if done_ids:
        print(f"Resuming — {len(done_ids)} markets already done.\n")

    if args.dry_run:
        pending_rows = [
            row for row in markets if not row.get("condition_id") or row.get("condition_id") not in done_ids
        ]
        print(f"Dry run only. Pending markets: {len(pending_rows)}")
        if pending_rows:
            sample = pending_rows[0]
            print(f"First pending market: {sample.get('title', '')}")
        return

    if "OPENAI_API_KEY" not in os.environ:
        raise SystemExit("OPENAI_API_KEY is not set.")

    OpenAI = require_openai_client_class()
    client = OpenAI()

    for index, row in enumerate(markets, start=1):
        condition_id = row.get("condition_id", "")
        title = row.get("title", "")

        if condition_id and condition_id in done_ids:
            print(f"[{index:3}/{len(markets)}] SKIP (already done): {title[:60]}")
            continue

        print(f"[{index:3}/{len(markets)}] Forecasting: {title[:60]}...")

        try:
            forecast = forecast_one(
                client=client,
                row=row,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
                temperature=args.temperature,
            )
            status = "ok"
        except Exception as exc:  # pragma: no cover - runtime API failures are expected to be data-dependent
            print(f"  ERROR: {exc}")
            forecast = {"error": str(exc)}
            status = "error"

        result = {
            "condition_id": condition_id,
            "market_slug": row.get("market_slug", ""),
            "event_slug": row.get("event_slug", ""),
            "title": title,
            "category": row.get("category") or row.get("domain", ""),
            "close_time": row.get("close_time") or row.get("close_date", ""),
            "actual_resolution": row.get("resolution") or row.get("actual_resolution", ""),
            "volume": row.get("volume", ""),
            "status": status,
            "forecast": forecast,
        }
        results.append(result)
        if condition_id:
            done_ids.add(condition_id)
        save_results(results, output_path)

        if args.sleep_between_calls > 0:
            time.sleep(args.sleep_between_calls)


if __name__ == "__main__":
    main()
