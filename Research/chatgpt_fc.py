#!/usr/bin/env python3
"""
Forecast future Polymarket markets with ChatGPT via the OpenAI Responses API.

This mirrors ``Research/chatgpt_recall.py`` but targets future events:
  1. Read market rows from newmarkets.csv.
  2. Build a forecasting prompt per row.
  3. Request structured JSON output from ChatGPT.
  4. Save results after every row so interrupted runs can resume.

Typical usage once credentials are configured:
    pip install openai
    export OPENAI_API_KEY=sk-...
    python Research/chatgpt_fc.py
"""
from __future__ import annotations

import argparse
import configparser
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

_cfg = configparser.ConfigParser(interpolation=None)
BASE_DIR = Path(__file__).parent
GAMMA_API = "https://gamma-api.polymarket.com"
CONFIG_PATH = BASE_DIR / "fc_config.txt"
_cfg.read(CONFIG_PATH, encoding="utf-8")

MARKET = _cfg.get("paths", "market")

DEFAULT_INPUT = BASE_DIR / MARKET / "newmarkets.csv"
DEFAULT_OUTPUT = BASE_DIR / MARKET / "forecast" / "gpt-5-5_fc.json"

DEFAULT_MODEL               = _cfg.get("models",          "openai_model",        fallback=os.environ.get("OPENAI_MODEL", "gpt-4o-2024-08-06"))
DEFAULT_MAX_OUTPUT_TOKENS   = _cfg.getint("hyperparameters", "max_tokens",        fallback=500)
DEFAULT_TEMPERATURE         = _cfg.getfloat("hyperparameters", "temperature",     fallback=0.0)
DEFAULT_SLEEP_BETWEEN_CALLS = _cfg.getfloat("hyperparameters", "sleep_between_calls", fallback=0.5)

_SYSTEM_PROMPT_FALLBACK = (
    "You are an AI assistant specialized in analyzing and predicting real-world events. "
    "Return JSON only; no extra text."
)
SYSTEM_PROMPT = _cfg.get("system_prompt", "prompt", fallback=_SYSTEM_PROMPT_FALLBACK).strip()


def fetch_market_price(market_slug: str) -> dict | None:
    if not market_slug:
        return None
    try:
        r = requests.get(f"{GAMMA_API}/markets", params={"slug": market_slug}, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"    [warn] price fetch failed for {market_slug}: {e}")
        return None
    markets = data if isinstance(data, list) else [data]
    for market in markets:
        raw_outcomes = market.get("outcomes", "[]")
        raw_prices = market.get("outcomePrices", "[]")
        try:
            outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
            prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices
        except Exception:
            continue
        if outcomes and prices and len(outcomes) == len(prices):
            return {o: float(p) for o, p in zip(outcomes, prices)}
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forecast future Polymarket events with ChatGPT.")
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
        "Resolves Yes if the condition in the title is met before "
        "the close time; resolves No otherwise."
    )

    outcomes_block = "\n".join(f"- {o}" for o in outcomes)

    return f"""\
Here is the given event:
Event title: {title}
Category: {category}
Close time (UTC): {close_time}
Possible outcomes:
{outcomes_block}
Example rule excerpt: {rule_text}\
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
        return [str(item).strip() for item in parsed if str(item).strip()]

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
                "description": "Concise 2-3 sentence rationale.",
            },
            "probabilities": {
                "type": "object",
                "properties": probability_properties,
                "required": list(outcomes),
                "additionalProperties": False,
            },
        },
        "required": ["rationale", "probabilities"],
        "additionalProperties": False,
    }


def validate_forecast_payload(payload: dict[str, Any], outcomes: list[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("response payload is not a JSON object")

    if "error" in payload:
        return payload

    rationale = payload.get("rationale")
    probabilities = payload.get("probabilities")

    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("missing or invalid rationale")
    if not isinstance(probabilities, dict):
        raise ValueError("missing or invalid probabilities object")
    if set(probabilities) != set(outcomes):
        raise ValueError(
            f"probability keys {sorted(probabilities)} do not match expected outcomes {sorted(outcomes)}"
        )
    normalized: dict[str, float] = {}
    for outcome in outcomes:
        value = probabilities.get(outcome)
        if not isinstance(value, (int, float)):
            raise ValueError(f"probability for {outcome!r} is not numeric")
        numeric = float(value)
        if numeric < 0.0 or numeric > 1.0:
            raise ValueError(f"probability for {outcome!r} is outside [0,1]")
        normalized[outcome] = numeric

    return {
        "rationale": rationale.strip(),
        "probabilities": normalized,
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
        if getattr(item, "type", None) != "message":
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
        text={
            "format": {
                "type": "json_schema",
                "name": "market_forecast",
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
    print(f"Market:  {MARKET}")
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
            print(f"First pending market: {pending_rows[0].get('title', '')}")
        return

    api_key_from_cfg = _cfg.get("api_keys", "OPENAI_API_KEY", fallback="UNSET").strip()
    if api_key_from_cfg and api_key_from_cfg != "UNSET":
        os.environ["OPENAI_API_KEY"] = api_key_from_cfg

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
        except Exception as exc:
            print(f"  ERROR: {exc}")
            forecast = {"error": str(exc)}
            status = "error"

        market_price = fetch_market_price(row.get("market_slug", ""))

        result = {
            "condition_id": condition_id,
            "market_slug": row.get("market_slug", ""),
            "event_slug": row.get("event_slug", ""),
            "title": title,
            "category": row.get("category") or row.get("domain", ""),
            "close_time": row.get("close_time") or row.get("close_date", ""),
            "volume": row.get("volume", ""),
            "status": status,
            "forecast": forecast,
        }
        if market_price is not None:
            result["market_price"] = market_price
        results.append(result)
        if condition_id:
            done_ids.add(condition_id)
        save_results(results, output_path)

        if args.sleep_between_calls > 0:
            time.sleep(args.sleep_between_calls)

    print(f"\nDone.  {len(results)} results saved to {output_path}")


if __name__ == "__main__":
    main()
