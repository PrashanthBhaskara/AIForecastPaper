#!/usr/bin/env bash
# Run a single chatgpt_recall.py command by index.
#
# Usage: ./jason.sh <index>
#
# Valid indices: 0..17
#
#   markets.csv:
#     0   ClimateMarkets             (--limit 100)
#     1   CommoditiesMarkets         (--limit 150)
#     2   CompaniesMarkets           (--limit 150)
#     3   EconomicsMarkets           (--limit 150)
#     4   ElectionsMarkets           (--limit 150)
#     5   EntertainmentMarkets       (--limit 150)
#     6   FinancialsMarkets          (--limit 150)
#     7   PoliticsMarkets            (--limit 150)
#     8   ScienceTechnologyMarkets   (--limit 150)
#
#   newmarkets.csv:
#     9   ClimateMarkets             (--limit 100)
#    10   CommoditiesMarkets         (--limit 150)
#    11   CompaniesMarkets           (--limit 150)
#    12   EconomicsMarkets           (--limit 150)
#    13   ElectionsMarkets           (--limit 150)
#    14   EntertainmentMarkets       (--limit 150)
#    15   FinancialsMarkets          (--limit 150)
#    16   PoliticsMarkets            (--limit 150)
#    17   ScienceTechnologyMarkets   (--limit 150)

set -euo pipefail

COMMANDS=(
  "./venv/bin/python Research/chatgpt_recall.py --input Research/ClimateMarkets/markets.csv            --limit 100 --output Research/ClimateMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/CommoditiesMarkets/markets.csv        --limit 150 --output Research/CommoditiesMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/CompaniesMarkets/markets.csv          --limit 150 --output Research/CompaniesMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/EconomicsMarkets/markets.csv          --limit 150 --output Research/EconomicsMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/ElectionsMarkets/markets.csv          --limit 150 --output Research/ElectionsMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/EntertainmentMarkets/markets.csv      --limit 150 --output Research/EntertainmentMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/FinancialsMarkets/markets.csv         --limit 150 --output Research/FinancialsMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/PoliticsMarkets/markets.csv           --limit 150 --output Research/PoliticsMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/ScienceTechnologyMarkets/markets.csv  --limit 150 --output Research/ScienceTechnologyMarkets/recall/chatgpt_recall.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/ClimateMarkets/newmarkets.csv            --limit 100 --output Research/ClimateMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/CommoditiesMarkets/newmarkets.csv        --limit 150 --output Research/CommoditiesMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/CompaniesMarkets/newmarkets.csv          --limit 150 --output Research/CompaniesMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/EconomicsMarkets/newmarkets.csv          --limit 150 --output Research/EconomicsMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/ElectionsMarkets/newmarkets.csv          --limit 150 --output Research/ElectionsMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/EntertainmentMarkets/newmarkets.csv      --limit 150 --output Research/EntertainmentMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/FinancialsMarkets/newmarkets.csv         --limit 150 --output Research/FinancialsMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/PoliticsMarkets/newmarkets.csv           --limit 150 --output Research/PoliticsMarkets/recall/chatgpt_recall_new.json"
  "./venv/bin/python Research/chatgpt_recall.py --input Research/ScienceTechnologyMarkets/newmarkets.csv  --limit 150 --output Research/ScienceTechnologyMarkets/recall/chatgpt_recall_new.json"
)

MAX_INDEX=$((${#COMMANDS[@]} - 1))

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <index>  (valid: 0..${MAX_INDEX})" >&2
  exit 2
fi

INDEX=$1

if ! [[ "$INDEX" =~ ^[0-9]+$ ]]; then
  echo "Error: index must be a non-negative integer (got: '$INDEX')" >&2
  exit 2
fi

if (( INDEX > MAX_INDEX )); then
  echo "Error: index $INDEX out of range (valid: 0..${MAX_INDEX})" >&2
  exit 2
fi

echo "[jason.sh] index $INDEX:"
echo "  ${COMMANDS[$INDEX]}"
echo
eval "${COMMANDS[$INDEX]}"
