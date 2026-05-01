#!/usr/bin/env python3
"""
Forecast future Polymarket markets with Gemini via the google-genai SDK.

This mirrors ``Research/gemini_recall.py`` but targets future events:
  1. Read market rows from newmarkets.csv.
  2. Build a forecasting prompt per row.
  3. Request JSON output from Gemini.
  4. Save results after every row so interrupted runs can resume.

Typical usage:
    pip install google-genai python-dotenv
    # add GEMINI_API_KEY=... to .env
    python Research/gemini_fc.py
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


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "fc_config.txt"

_cfg = configparser.ConfigParser(interpolation=None)
_cfg.read(CONFIG_PATH, encoding="utf-8")

MARKET = _cfg.get("paths", "market")

DEFAULT_INPUT = BASE_DIR / MARKET / "newmarkets.csv"
DEFAULT_OUTPUT = BASE_DIR / MARKET / "forecast" / "gemini-3-flash-preview_fc.json"

DEFAULT_MODEL               = _cfg.get("models",          "gemini_model",        fallback=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
DEFAULT_MAX_OUTPUT_TOKENS   = _cfg.getint("hyperparameters", "max_tokens",        fallback=500)
DEFAULT_TEMPERATURE         = _cfg.getfloat("hyperparameters", "temperature",     fallback=0.0)
DEFAULT_SLEEP_BETWEEN_CALLS = _cfg.getfloat("hyperparameters", "sleep_between_calls", fallback=0.5)

_SYSTEM_PROMPT_FALLBACK = (
    "You are an AI assistant specialized in analyzing and predicting real-world events. "
    "Return JSON only; no extra text."
)
SYSTEM_PROMPT = _cfg.get("system_prompt", "prompt", fallback=_SYSTEM_PROMPT_FALLBACK).strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forecast future Polymarket events with Gemini.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to input CSV.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of markets to process.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model. Default: {DEFAULT_MODEL}")
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
        "--max-retries",
        type=int,
        default=2,
        help="Retry attempts on parse/validation failure (each bumps temperature). Default: 2",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and show planned work without calling the Gemini API.",
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
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
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
            },
        },
        "required": ["rationale", "probabilities"],
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


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return
    env_path = BASE_DIR.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def require_genai_module():
    try:
        from google import genai
        from google.genai import types as genai_types
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "google-genai SDK not installed. Install it with `pip install google-genai`."
        ) from exc
    return genai, genai_types


def response_output_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    pieces: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text:
                pieces.append(part_text)
    return "".join(pieces)


def is_retryable_503_error(exc: Exception) -> bool:
    message = str(exc).upper()
    return "503" in message and "UNAVAILABLE" in message


def thinking_config_for_model(genai_types: Any, model: str) -> Any | None:
    normalized = model.strip().lower()

    if normalized.startswith("gemini-3"):
        if "flash" in normalized:
            return genai_types.ThinkingConfig(thinking_level="minimal")
        return genai_types.ThinkingConfig(thinking_level="low")

    if normalized.startswith("gemini-2.5"):
        if "flash" in normalized:
            return genai_types.ThinkingConfig(thinking_budget=0)
        return None

    return genai_types.ThinkingConfig(thinking_budget=0)


def _attempt_forecast(
    client: Any,
    genai_types: Any,
    user_prompt: str,
    outcomes: list[str],
    model: str,
    max_output_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    config_kwargs = dict(
        system_instruction=SYSTEM_PROMPT,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
        response_schema=response_schema(outcomes),
    )
    thinking_config = thinking_config_for_model(genai_types, model)
    if thinking_config is not None:
        config_kwargs["thinking_config"] = thinking_config
    config = genai_types.GenerateContentConfig(**config_kwargs)

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=config,
    )

    raw_text = response_output_text(response)
    parsed = parse_json_response(raw_text)
    if "error" in parsed:
        raise ValueError(parsed["error"])
    return validate_forecast_payload(parsed, outcomes)


def forecast_one(
    client: Any,
    genai_types: Any,
    row: dict[str, str],
    model: str,
    max_output_tokens: int,
    temperature: float,
    max_retries: int = 2,
    retry_temperature_step: float = 0.3,
) -> dict[str, Any]:
    outcomes = infer_outcomes(row)
    user_prompt = build_user_prompt(row, outcomes)

    last_err: Exception | None = None
    attempts = max_retries + 1
    for attempt in range(attempts):
        attempt_temp = temperature if attempt == 0 else max(
            temperature + retry_temperature_step * attempt,
            retry_temperature_step,
        )
        while True:
            try:
                return _attempt_forecast(
                    client=client,
                    genai_types=genai_types,
                    user_prompt=user_prompt,
                    outcomes=outcomes,
                    model=model,
                    max_output_tokens=max_output_tokens,
                    temperature=attempt_temp,
                )
            except Exception as exc:
                if is_retryable_503_error(exc):
                    print("  503 UNAVAILABLE from Gemini; retrying in 5.0s")
                    time.sleep(5.0)
                    continue
                if isinstance(exc, ValueError):
                    last_err = exc
                    if attempt < attempts - 1:
                        next_temp = max(
                            temperature + retry_temperature_step * (attempt + 1),
                            retry_temperature_step,
                        )
                        print(
                            f"  retry {attempt + 1}/{max_retries} at temp={next_temp:.2f} "
                            f"after parse/validation failure: {str(exc)[:80]}"
                        )
                    break
                raise

    raise RuntimeError(f"all {attempts} attempts failed; last error: {last_err}")


def validate_args(args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit < 0:
        raise SystemExit("--limit must be zero or positive")
    if args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be positive")
    if args.sleep_between_calls < 0:
        raise SystemExit("--sleep-between-calls must be zero or positive")
    if args.max_retries < 0:
        raise SystemExit("--max-retries must be zero or positive")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)

    load_dotenv_if_available()

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

    api_key_from_cfg = _cfg.get("api_keys", "GEMINI_API_KEY", fallback="UNSET").strip()
    if api_key_from_cfg and api_key_from_cfg != "UNSET":
        os.environ["GEMINI_API_KEY"] = api_key_from_cfg

    if "GEMINI_API_KEY" not in os.environ:
        raise SystemExit("GEMINI_API_KEY is not set (checked env, .env, and fc_config.txt).")

    genai, genai_types = require_genai_module()
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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
                genai_types=genai_types,
                row=row,
                model=args.model,
                max_output_tokens=args.max_output_tokens,
                temperature=args.temperature,
                max_retries=args.max_retries,
            )
            status = "ok"
        except Exception as exc:
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

    print(f"\nDone.  {len(results)} results saved to {output_path}")


if __name__ == "__main__":
    main()
