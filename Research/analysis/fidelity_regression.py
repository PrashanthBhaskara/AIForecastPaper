"""
Recall fidelity → forecast Brier score regression analysis.

Builds R_{m,d}: per-model, per-domain recall fidelity vector using recall_score.
Regresses forecast Brier on R_{m,d} with domain difficulty controls and model FEs.

recall_score encoding:
  1.0 = correct outcome + clean reasoning
  0.5 = correct outcome, wrong/partial reasoning
  0.0 = wrong outcome
  null = didn't recall (treated as 0.0 in R_{m,d})

Domain difficulty: mean binary entropy of open-market prices (from forecast/*.json).
  High entropy = market uncertain = harder domain.
"""

import glob
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
import statsmodels.formula.api as smf
import statsmodels.api as sm

RESEARCH_DIR = Path(__file__).parent.parent

DOMAINS = [
    "ClimateMarkets",
    "CommoditiesMarkets",
    "CompaniesMarkets",
    "EconomicsMarkets",
    "ElectionsMarkets",
    "EntertainmentMarkets",
    "FinancialsMarkets",
    "PoliticsMarkets",
    "ScienceTechnologyMarkets",
]

# Clean domain label for display
def short_domain(d):
    return d.replace("Markets", "")


def binary_entropy(p):
    p = max(min(float(p), 1 - 1e-10), 1e-10)
    return -p * math.log(p) - (1 - p) * math.log(1 - p)


# ── Step 1: Load recall records ───────────────────────────────────────────────

def load_recall_records():
    """
    Returns list of dicts with keys:
      model, domain, condition_id, actual_resolution,
      recall_score (float or None), p_yes (float or None)
    """
    records = []
    for domain in DOMAINS:
        recall_dir = RESEARCH_DIR / domain / "recall"
        for path in sorted(recall_dir.glob("*.json")):
            model = path.stem.replace("_recall", "")
            try:
                items = json.loads(path.read_text())
            except Exception as e:
                print(f"[WARN] {path}: {e}")
                continue
            for item in items:
                fc = item.get("forecast") or {}
                ra = fc.get("recall_assessment") or {}
                probs = fc.get("probabilities") or {}
                p_yes = probs.get("Yes")
                actual = item.get("actual_resolution")
                score = ra.get("recall_score")  # float or None
                records.append({
                    "model": model,
                    "domain": domain,
                    "condition_id": item.get("condition_id", ""),
                    "actual_resolution": actual,
                    "recall_score": score,
                    "p_yes": p_yes,
                    "recalled_outcome": ra.get("recalled_outcome_if_known"),
                    "grader_verdict": ra.get("grader_verdict"),
                })
    return records


# ── Step 2: Domain difficulty from open-market entropy ───────────────────────

def compute_domain_difficulty():
    """
    For each domain, compute mean binary entropy of market p(Yes) across all
    open forecast files. Uses all available models' fc files (entropy is a
    property of the market, not the model) and deduplicates by condition_id.
    """
    difficulty = {}
    for domain in DOMAINS:
        fc_dir = RESEARCH_DIR / domain / "forecast"
        seen = {}
        for path in sorted(fc_dir.glob("*.json")):
            try:
                items = json.loads(path.read_text())
            except Exception:
                continue
            for item in items:
                cid = item.get("condition_id", "")
                mp = item.get("market_price") or {}
                p = mp.get("Yes")
                if p is not None and cid not in seen:
                    seen[cid] = float(p)
        if seen:
            prices = list(seen.values())
            difficulty[domain] = {
                "mean_entropy": np.mean([binary_entropy(p) for p in prices]),
                "naive_brier": np.mean([(p - 0.5) ** 2 for p in prices]),
                "n_markets": len(prices),
            }
    return difficulty


# ── Step 3: Per-model, per-domain fidelity vector R_{m,d} ───────────────────

def build_fidelity_matrix(records):
    """
    R_{m,d} = mean recall_score for scored items (None = not recognized = 0.0).

    A model is considered "ungraded" for a (model, domain) cell if NO item in that
    cell has a recall_score value — the recall file was never run through the grader.
    Ungraded cells get R_md = NaN so they are excluded from regression.

    For graded models, null recall_score means the model did not recognize the
    event (a legitimate 0.0 fidelity observation).
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for r in records:
        buckets[(r["model"], r["domain"])].append(r)

    rows = []
    for (model, domain), items in sorted(buckets.items()):
        # Check if this (model, domain) cell has been graded at all
        any_graded = any(r["recall_score"] is not None for r in items)

        # For graded models: null → 0.0 (model didn't recognize = 0 fidelity)
        # For ungraded models: R_md = NaN
        if any_graded:
            fidelity_scores = [
                r["recall_score"] if r["recall_score"] is not None else 0.0
                for r in items
            ]
            R_md = float(np.mean(fidelity_scores))
        else:
            fidelity_scores = []
            R_md = np.nan

        fidelity_scores_graded = [r["recall_score"] for r in items
                                   if r["recall_score"] is not None]

        # Forecast Brier vs actual outcome
        brier_scores = []
        for r in items:
            p = r["p_yes"]
            actual = r["actual_resolution"]
            if p is not None and actual in ("Yes", "No"):
                outcome = 1.0 if actual == "Yes" else 0.0
                brier_scores.append((p - outcome) ** 2)

        # "Confident wrong" = recall_score 0.0 AND model stated an answer
        confident_wrong = [r for r in items
                           if r["recall_score"] == 0.0
                           and r["recalled_outcome"] is not None]

        # Count breakdown from graded items only (not null→0 substituted)
        n_graded = len(fidelity_scores_graded)
        rows.append({
            "model": model,
            "domain": domain,
            "graded": any_graded,
            "n_items": len(items),
            "R_md": R_md,
            "R_md_excl_null": (float(np.mean(fidelity_scores_graded))
                               if fidelity_scores_graded else np.nan),
            "n_graded": n_graded,
            "n_null": sum(1 for r in items if r["recall_score"] is None),
            "n_correct": sum(1 for r in items if r["recall_score"] == 1.0),
            "n_partial": sum(1 for r in items if r["recall_score"] == 0.5),
            "n_wrong_explicit": sum(1 for r in items if r["recall_score"] == 0.0),
            "n_confident_wrong": len(confident_wrong),
            "mean_brier": np.mean(brier_scores) if brier_scores else np.nan,
            "n_brier": len(brier_scores),
        })
    return rows


# ── Step 4: Regression ───────────────────────────────────────────────────────

def run_regression(panel_rows, difficulty):
    """
    Brier_{m,d} = α + β·R_{m,d} + γ·Difficulty_d + model_FE + ε

    panel_rows: list of dicts from build_fidelity_matrix
    difficulty: dict domain → {mean_entropy, ...}

    Returns fitted OLS result.
    """
    import pandas as pd

    rows = []
    for r in panel_rows:
        domain = r["domain"]
        # Only include graded cells with enough resolved items for Brier
        if not r["graded"] or r["n_brier"] < 5:
            continue
        diff = difficulty.get(domain, {})
        if not diff:
            continue
        rows.append({
            "model": r["model"],
            "domain": domain,
            "brier": r["mean_brier"],
            "R_md": r["R_md"],
            "R_md_excl_null": r["R_md_excl_null"],
            "difficulty": diff["mean_entropy"],
            "naive_brier": diff["naive_brier"],
        })

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["brier", "R_md", "difficulty"])

    n_models = df["model"].nunique()
    print(f"\nRegression dataset: {len(df)} (model×domain) cells "
          f"across {n_models} model(s), {df['domain'].nunique()} domains")
    if n_models == 1:
        print("  NOTE: Only one model has graded recall scores (gpt-5-5). "
              "Model FE is collinear with intercept — M3 reduces to M2.")

    results = {}

    # Model 1: Simple bivariate (no controls)
    m1 = smf.ols("brier ~ R_md", data=df).fit()
    results["m1_simple"] = m1

    # Model 2: With domain difficulty control
    m2 = smf.ols("brier ~ R_md + difficulty", data=df).fit()
    results["m2_difficulty"] = m2

    # Model 3: Full model with model fixed effects (C() creates dummies)
    m3 = smf.ols("brier ~ R_md + difficulty + C(model)", data=df).fit()
    results["m3_model_fe"] = m3

    # Model 4: Excluding nulls (R_md_excl_null) with FE
    df_excl = df.dropna(subset=["R_md_excl_null"])
    if len(df_excl) > len(df["model"].unique()) + 3:
        m4 = smf.ols("brier ~ R_md_excl_null + difficulty + C(model)", data=df_excl).fit()
        results["m4_excl_null_fe"] = m4

    return results, df


# ── Step 5: Per-domain fidelity table ────────────────────────────────────────

def print_fidelity_table(panel_rows, difficulty):
    models = sorted(set(r["model"] for r in panel_rows))
    domains = DOMAINS

    print("\n" + "=" * 80)
    print("PER-MODEL, PER-DOMAIN RECALL FIDELITY  R_{m,d}  (null → 0.0)")
    print("=" * 80)
    col_w = 11
    header = f"{'Model':<34}" + "".join(f"{short_domain(d)[:col_w]:>{col_w}}" for d in domains)
    print(header)
    print("-" * len(header))

    lookup = {(r["model"], r["domain"]): r for r in panel_rows}
    for model in models:
        row_str = f"{model:<34}"
        for d in domains:
            r = lookup.get((model, d))
            if r is None or not r["graded"]:
                row_str += f"{'—':>{col_w}}"
            else:
                row_str += f"{r['R_md']:>{col_w}.3f}"
        print(row_str)

    # Domain row: difficulty
    print()
    diff_row = f"{'Domain difficulty (entropy)':<34}"
    for d in domains:
        diff = difficulty.get(d, {})
        val = diff.get("mean_entropy")
        diff_row += f"{val:>{col_w}.3f}" if val is not None else f"{'—':>{col_w}}"
    print(diff_row)


def print_score_breakdown(panel_rows):
    print("\n" + "=" * 80)
    print("RECALL SCORE BREAKDOWN  (graded items only)  PER MODEL")
    print("1.0=correct+clean  0.5=correct+errors  0.0=wrong  null=not recognized")
    print("=" * 80)
    from collections import defaultdict
    by_model = defaultdict(lambda: {"n": 0, "graded": 0, "c1": 0, "c5": 0, "c0_expl": 0, "null": 0, "cw": 0})
    for r in panel_rows:
        m = r["model"]
        by_model[m]["n"] += r["n_items"]
        by_model[m]["graded"] += r["n_graded"]
        by_model[m]["c1"] += r["n_correct"]
        by_model[m]["c5"] += r["n_partial"]
        by_model[m]["c0_expl"] += r["n_wrong_explicit"]
        by_model[m]["null"] += r["n_null"]
        by_model[m]["cw"] += r["n_confident_wrong"]

    print(f"{'Model':<34} {'N':>6} {'graded':>7}  "
          f"{'1.0 (%)':>9} {'0.5 (%)':>9} {'0.0 (%)':>9} {'no-recall (%)':>14} {'conf_wrong':>11}")
    print("-" * 105)
    for model in sorted(by_model):
        s = by_model[model]
        n = s["n"]
        g = s["graded"]
        if g == 0:
            print(f"{model:<34} {n:>6} {'—':>7}  {'(ungraded)':>9}")
            continue
        print(f"{model:<34} {n:>6} {g:>7}  "
              f"{s['c1']:>4} ({100*s['c1']/g:3.0f}%)  "
              f"{s['c5']:>4} ({100*s['c5']/g:3.0f}%)  "
              f"{s['c0_expl']:>4} ({100*s['c0_expl']/g:3.0f}%)  "
              f"{s['null']:>5} ({100*s['null']/g:3.0f}%)  "
              f"{s['cw']:>6}")


def print_confident_wrong(records):
    print("\n" + "=" * 80)
    print("CONFIDENT WRONG SUBSET  (recall_score=0.0, had a recalled answer)")
    print("gpt-5-5 only")
    print("=" * 80)
    cw = [r for r in records
          if r["model"] == "gpt-5-5"
          and r["recall_score"] == 0.0
          and r["recalled_outcome"] is not None]
    by_domain = defaultdict(list)
    for r in cw:
        by_domain[r["domain"]].append(r)

    print(f"{'Domain':<30} {'Count':>6}")
    print("-" * 40)
    for d in DOMAINS:
        items = by_domain.get(d, [])
        print(f"{short_domain(d):<30} {len(items):>6}")
    print(f"{'Total':<30} {len(cw):>6}")


def print_regression_summary(results):
    print("\n" + "=" * 80)
    print("REGRESSION:  Brier_{m,d} = α + β·R_{m,d} + γ·Difficulty_d + model_FE")
    print("=" * 80)

    labels = {
        "m1_simple":       "M1: Brier ~ R_md",
        "m2_difficulty":   "M2: Brier ~ R_md + difficulty",
        "m3_model_fe":     "M3: Brier ~ R_md + difficulty + model_FE   [HEADLINE]",
        "m4_excl_null_fe": "M4: Brier ~ R_excl_null + difficulty + model_FE",
    }

    for key, label in labels.items():
        if key not in results:
            continue
        res = results[key]
        print(f"\n{label}")
        print(f"  N={int(res.nobs)}, R²={res.rsquared:.3f}, adj-R²={res.rsquared_adj:.3f}")

        coef_rows = []
        for param in res.params.index:
            coef = res.params[param]
            se = res.bse[param]
            pval = res.pvalues[param]
            stars = "***" if pval < 0.001 else "**" if pval < 0.01 else "*" if pval < 0.05 else ""
            coef_rows.append((param, coef, se, pval, stars))

        # Print R_md / recall row prominently
        print(f"  {'Parameter':<40} {'Coef':>10} {'SE':>10} {'p':>10}  {'sig':>4}")
        print("  " + "-" * 78)
        for param, coef, se, pval, stars in coef_rows:
            highlight = " ◄" if "R_md" in param and "C(model)" not in param else ""
            print(f"  {param:<40} {coef:>10.4f} {se:>10.4f} {pval:>10.4f}  {stars:>4}{highlight}")

    # Print the headline β coefficient
    if "m3_model_fe" in results:
        res = results["m3_model_fe"]
        beta = res.params.get("R_md", np.nan)
        se = res.bse.get("R_md", np.nan)
        pval = res.pvalues.get("R_md", np.nan)
        ci_lo, ci_hi = res.conf_int().loc["R_md"] if "R_md" in res.conf_int().index else (np.nan, np.nan)
        print(f"\n{'─'*60}")
        print(f"HEADLINE: β(recall fidelity) = {beta:.4f}  "
              f"SE={se:.4f}  p={pval:.4f}  95%CI=[{ci_lo:.4f}, {ci_hi:.4f}]")
        direction = "lower" if beta < 0 else "higher"
        print(f"  A 1-unit increase in R_{{m,d}} is associated with "
              f"{abs(beta):.4f} {direction} Brier score (within model).")
        print(f"{'─'*60}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit("pandas required: pip install pandas statsmodels")

    print("Loading recall records...")
    records = load_recall_records()
    print(f"  {len(records)} records across "
          f"{len(set(r['model'] for r in records))} models, "
          f"{len(set(r['domain'] for r in records))} domains")

    print("Computing domain difficulty...")
    difficulty = compute_domain_difficulty()
    for d, v in sorted(difficulty.items()):
        print(f"  {short_domain(d):<22} entropy={v['mean_entropy']:.4f}  "
              f"naive_brier={v['naive_brier']:.4f}  n={v['n_markets']}")

    print("Building fidelity matrix...")
    panel_rows = build_fidelity_matrix(records)

    print_score_breakdown(panel_rows)
    print_fidelity_table(panel_rows, difficulty)
    print_confident_wrong(records)

    print("\nRunning regressions...")
    results, df = run_regression(panel_rows, difficulty)
    print_regression_summary(results)

    # Save panel data for further analysis
    out_path = RESEARCH_DIR / "analysis" / "panel_data.csv"
    df.to_csv(out_path, index=False)
    print(f"\nPanel data saved to {out_path}")


if __name__ == "__main__":
    main()
