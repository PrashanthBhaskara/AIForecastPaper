#!/usr/bin/env bash
# Run chatgpt_fc.py over every market's newmarkets.csv, sequentially.
# Resumable: each per-market run skips condition_ids already in its output JSON.

export PYTHONUNBUFFERED=1

REPO="/Users/jason/Documents/AIForecastPaper"
PYTHON="$REPO/venv/bin/python"
SCRIPT="$REPO/Research/chatgpt_fc.py"
MODEL_TAG="gpt-5-5"
LOG="$REPO/all_newmarkets.log"

MARKETS=(
  ClimateMarkets
  CommoditiesMarkets
  CompaniesMarkets
  EconomicsMarkets
  ElectionsMarkets
  EntertainmentMarkets
  FinancialsMarkets
  PoliticsMarkets
  ScienceTechnologyMarkets
)

cd "$REPO" || exit 1

if [ -z "$OPENAI_API_KEY" ]; then
  echo "OPENAI_API_KEY is not set in the environment." | tee -a "$LOG"
  echo "Either export it before running, or set it in Research/fc_config.txt." | tee -a "$LOG"
  exit 1
fi

echo "===== START $(date '+%Y-%m-%d %H:%M:%S') =====" | tee -a "$LOG"

for market in "${MARKETS[@]}"; do
  input="Research/$market/newmarkets.csv"
  output="Research/$market/forecast/${MODEL_TAG}_fc.json"

  if [ ! -f "$input" ]; then
    echo "[$(date '+%H:%M:%S')] SKIP $market (no $input)" | tee -a "$LOG"
    continue
  fi

  echo "" | tee -a "$LOG"
  echo "[$(date '+%H:%M:%S')] >>> $market" | tee -a "$LOG"
  "$PYTHON" "$SCRIPT" --input "$input" --output "$output" 2>&1 | tee -a "$LOG"
  status=${PIPESTATUS[0]}
  echo "[$(date '+%H:%M:%S')] <<< $market exit=$status" | tee -a "$LOG"
done

echo "" | tee -a "$LOG"
echo "===== END $(date '+%Y-%m-%d %H:%M:%S') =====" | tee -a "$LOG"
