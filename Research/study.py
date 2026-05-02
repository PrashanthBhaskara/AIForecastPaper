"""
Study script: aggregates recall and forecast JSON files across Research subdirectories.

Recall metrics (vs actual_resolution):
  - recall_rate: fraction of events recognized
  - accuracy: fraction correctly recalled (non-null)
  - Brier score: (p_yes - outcome)^2

Forecast metrics (vs market_price, used as calibration reference):
  - mean_brier_vs_market: (model_p_yes - market_p_yes)^2
  - mean_abs_diff: |model_p_yes - market_p_yes|
  - mean_model_p_yes / mean_market_p_yes
"""

import json
from collections import defaultdict
from pathlib import Path

RESEARCH_DIR = Path(__file__).parent


# ── Recall ────────────────────────────────────────────────────────────────────

def load_all_recall_records():
    records = []
    for json_path in sorted(RESEARCH_DIR.rglob("*/recall/*.json")):
        model = json_path.stem.replace("_recall", "")
        try:
            data = json.loads(json_path.read_text())
        except Exception as e:
            print(f"  [WARN] Could not parse {json_path}: {e}")
            continue
        if not isinstance(data, list):
            data = [data]
        for entry in data:
            records.append((entry, model))
    return records


def parse_recall_entry(entry):
    actual = entry.get("actual_resolution")
    category = entry.get("category", "Unknown")
    forecast = entry.get("forecast") or {}
    ra = forecast.get("recall_assessment") or {}
    recalled = ra.get("recalled_outcome_if_known")
    recognized = ra.get("recognized_event")
    probs = forecast.get("probabilities") or {}
    p_yes = probs.get("Yes")
    return {
        "actual": actual,
        "category": category,
        "recalled": recalled,
        "recognized": recognized,
        "p_yes": p_yes,
    }


def brier(p_yes, actual_resolution):
    if p_yes is None or actual_resolution is None:
        return None
    outcome = 1.0 if actual_resolution == "Yes" else 0.0
    return (p_yes - outcome) ** 2


def compute_recall_stats(rows):
    n = len(rows)
    nulls = sum(1 for r in rows if r["recalled"] is None)
    recognized = sum(1 for r in rows if r["recognized"] is True)
    non_null = [r for r in rows if r["recalled"] is not None]
    correct = sum(1 for r in non_null if r["recalled"] == r["actual"])

    brier_scores = [brier(r["p_yes"], r["actual"]) for r in rows]
    valid_brier = [b for b in brier_scores if b is not None]

    recall_rate = recognized / n if n else None
    accuracy = correct / len(non_null) if non_null else None
    mean_brier = sum(valid_brier) / len(valid_brier) if valid_brier else None

    return {
        "n": n,
        "nulls": nulls,
        "recognized": recognized,
        "recall_rate": recall_rate,
        "non_null": len(non_null),
        "correct": correct,
        "accuracy": accuracy,
        "brier_n": len(valid_brier),
        "mean_brier": mean_brier,
    }


# ── Forecast ──────────────────────────────────────────────────────────────────

def load_all_forecast_records():
    records = []
    for json_path in sorted(RESEARCH_DIR.rglob("*/forecast/*.json")):
        model = json_path.stem.replace("_fc", "")
        try:
            data = json.loads(json_path.read_text())
        except Exception as e:
            print(f"  [WARN] Could not parse {json_path}: {e}")
            continue
        if not isinstance(data, list):
            data = [data]
        for entry in data:
            records.append((entry, model))
    return records


def parse_forecast_entry(entry):
    category = entry.get("category", "Unknown")
    status = entry.get("status", "")
    forecast = entry.get("forecast") or {}
    probs = forecast.get("probabilities") or {}
    model_p_yes = probs.get("Yes")
    market_price = entry.get("market_price") or {}
    market_p_yes = market_price.get("Yes")
    return {
        "category": category,
        "status": status,
        "model_p_yes": model_p_yes,
        "market_p_yes": market_p_yes,
    }


def compute_forecast_stats(rows):
    n = len(rows)
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_with_price = sum(1 for r in rows if r["market_p_yes"] is not None)

    comparable = [r for r in rows if r["model_p_yes"] is not None and r["market_p_yes"] is not None]
    brier_vs_market = [(r["model_p_yes"] - r["market_p_yes"]) ** 2 for r in comparable]
    abs_diffs = [abs(r["model_p_yes"] - r["market_p_yes"]) for r in comparable]

    model_ps = [r["model_p_yes"] for r in rows if r["model_p_yes"] is not None]
    market_ps = [r["market_p_yes"] for r in rows if r["market_p_yes"] is not None]

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    return {
        "n": n,
        "n_ok": n_ok,
        "n_with_price": n_with_price,
        "brier_n": len(comparable),
        "mean_brier_vs_market": mean(brier_vs_market),
        "mean_abs_diff": mean(abs_diffs),
        "mean_model_p_yes": mean(model_ps),
        "mean_market_p_yes": mean(market_ps),
    }


# ── Formatting ────────────────────────────────────────────────────────────────

def fmt(val, pct=False, decimals=4):
    if val is None:
        return "  N/A"
    if pct:
        return f"{val*100:.1f}%"
    return f"{val:.{decimals}f}"


def print_recall_stats(label, stats, indent=0):
    pad = " " * indent
    print(f"{pad}{label}")
    print(f"{pad}  Total conditions : {stats['n']}")
    print(f"{pad}  Nulls            : {stats['nulls']}  ({fmt(stats['nulls']/stats['n'] if stats['n'] else None, pct=True)} of total)")
    print(f"{pad}  Recognized       : {stats['recognized']}  ({fmt(stats['recall_rate'], pct=True)} recall rate)")
    print(f"{pad}  Non-null         : {stats['non_null']}")
    print(f"{pad}  Correct          : {stats['correct']}  ({fmt(stats['accuracy'], pct=True)} accuracy on non-null)")
    print(f"{pad}  Mean Brier score : {fmt(stats['mean_brier'])}  (n={stats['brier_n']})")


def print_forecast_stats(label, stats, indent=0):
    pad = " " * indent
    print(f"{pad}{label}")
    print(f"{pad}  Total markets    : {stats['n']}  (ok: {stats['n_ok']}, with market price: {stats['n_with_price']})")
    print(f"{pad}  Mean Brier vs market price : {fmt(stats['mean_brier_vs_market'])}  (n={stats['brier_n']})")
    print(f"{pad}  Mean |model - market| p(Yes): {fmt(stats['mean_abs_diff'])}")
    print(f"{pad}  Mean model p(Yes)  : {fmt(stats['mean_model_p_yes'])}")
    print(f"{pad}  Mean market p(Yes) : {fmt(stats['mean_market_p_yes'])}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    recall_records = load_all_recall_records()
    forecast_records = load_all_forecast_records()
    print(f"Loaded {len(recall_records)} recall pairs, {len(forecast_records)} forecast pairs from {RESEARCH_DIR}\n")

    # ── Group recall ──────────────────────────────────────────────────────────
    recall_by_model = defaultdict(list)
    recall_by_cat = defaultdict(list)
    all_recall_rows = []

    for entry, model in recall_records:
        row = parse_recall_entry(entry)
        row["model"] = model
        all_recall_rows.append(row)
        recall_by_model[model].append(row)
        recall_by_cat[row["category"]].append(row)

    # ── Group forecast ────────────────────────────────────────────────────────
    fc_by_model = defaultdict(list)
    fc_by_cat = defaultdict(list)
    all_fc_rows = []

    for entry, model in forecast_records:
        row = parse_forecast_entry(entry)
        row["model"] = model
        all_fc_rows.append(row)
        fc_by_model[model].append(row)
        fc_by_cat[row["category"]].append(row)

    all_models = sorted(set(list(recall_by_model) + list(fc_by_model)))
    all_cats = sorted(set(list(recall_by_cat) + list(fc_by_cat)))

    # ── Global stats ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("GLOBAL RECALL STATS")
    print("=" * 60)
    print_recall_stats("All models combined", compute_recall_stats(all_recall_rows))

    print()
    print("=" * 60)
    print("GLOBAL FORECAST STATS  (Brier vs market price as reference)")
    print("=" * 60)
    print_forecast_stats("All models combined", compute_forecast_stats(all_fc_rows))

    # ── Per-model stats ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PER-MODEL RECALL STATS")
    print("=" * 60)
    for model in all_models:
        if model in recall_by_model:
            print()
            print_recall_stats(model, compute_recall_stats(recall_by_model[model]), indent=2)

    print("\n" + "=" * 60)
    print("PER-MODEL FORECAST STATS")
    print("=" * 60)
    for model in all_models:
        if model in fc_by_model:
            print()
            print_forecast_stats(model, compute_forecast_stats(fc_by_model[model]), indent=2)

    # ── Per-category stats ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PER-CATEGORY RECALL STATS (all models)")
    print("=" * 60)
    for cat in all_cats:
        if cat in recall_by_cat:
            print()
            print_recall_stats(cat, compute_recall_stats(recall_by_cat[cat]), indent=2)

    print("\n" + "=" * 60)
    print("PER-CATEGORY FORECAST STATS (all models)")
    print("=" * 60)
    for cat in all_cats:
        if cat in fc_by_cat:
            print()
            print_forecast_stats(cat, compute_forecast_stats(fc_by_cat[cat]), indent=2)

    # ── Model × Category tables ───────────────────────────────────────────────
    col_w = 12

    recall_by_mc = defaultdict(lambda: defaultdict(list))
    for row in all_recall_rows:
        recall_by_mc[row["model"]][row["category"]].append(row)

    fc_by_mc = defaultdict(lambda: defaultdict(list))
    for row in all_fc_rows:
        fc_by_mc[row["model"]][row["category"]].append(row)

    print("\n" + "=" * 60)
    print("RECALL BRIER: MODEL × CATEGORY")
    print("=" * 60)
    header = f"{'Model':<30}" + "".join(f"{c[:col_w]:>{col_w}}" for c in all_cats)
    print(header)
    print("-" * len(header))
    for model in all_models:
        row_str = f"{model:<30}"
        for cat in all_cats:
            rows_mc = recall_by_mc[model][cat]
            if not rows_mc:
                row_str += f"{'—':>{col_w}}"
            else:
                s = compute_recall_stats(rows_mc)
                val = fmt(s["mean_brier"], decimals=3) if s["mean_brier"] is not None else "N/A"
                row_str += f"{val:>{col_w}}"
        print(row_str)

    print("\n" + "=" * 60)
    print("FORECAST BRIER VS MARKET: MODEL × CATEGORY")
    print("=" * 60)
    header = f"{'Model':<30}" + "".join(f"{c[:col_w]:>{col_w}}" for c in all_cats)
    print(header)
    print("-" * len(header))
    for model in all_models:
        row_str = f"{model:<30}"
        for cat in all_cats:
            rows_mc = fc_by_mc[model][cat]
            if not rows_mc:
                row_str += f"{'—':>{col_w}}"
            else:
                s = compute_forecast_stats(rows_mc)
                val = fmt(s["mean_brier_vs_market"], decimals=3) if s["mean_brier_vs_market"] is not None else "N/A"
                row_str += f"{val:>{col_w}}"
        print(row_str)

    # ── Side-by-side summary: recall Brier vs forecast Brier ─────────────────
    print("\n" + "=" * 60)
    print("SIDE-BY-SIDE: RECALL BRIER vs FORECAST BRIER (per model)")
    print("Forecast Brier is computed vs Polymarket price, not actual outcome.")
    print("=" * 60)
    print(f"{'Model':<30}  {'Recall Brier':>14}  {'Forecast Brier':>14}  {'N recall':>9}  {'N forecast':>10}")
    print("-" * 85)
    for model in all_models:
        r_rows = recall_by_model.get(model, [])
        f_rows = fc_by_model.get(model, [])
        rs = compute_recall_stats(r_rows) if r_rows else None
        fs = compute_forecast_stats(f_rows) if f_rows else None
        rb = fmt(rs["mean_brier"], decimals=4) if rs and rs["mean_brier"] is not None else "N/A"
        fb = fmt(fs["mean_brier_vs_market"], decimals=4) if fs and fs["mean_brier_vs_market"] is not None else "N/A"
        rn = rs["brier_n"] if rs else 0
        fn = fs["brier_n"] if fs else 0
        print(f"{model:<30}  {rb:>14}  {fb:>14}  {rn:>9}  {fn:>10}")


if __name__ == "__main__":
    main()
