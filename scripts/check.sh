#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf .pytest_cache
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
find . -name "*.pyc" -delete

echo "=== PYTEST ==="
python3 -m pytest -q

echo
echo "=== DOMAIN IMPORT CHECK ==="
if grep -R "repositories\|services" -n src/jeeves_dap/domain; then
  echo "FAIL: domain imports forbidden layer"
  exit 1
fi

echo
echo "=== MOJIBAKE CHECK ==="
if grep -R --include="*.py" "Ω\|µ\|æ\|Ç\|∞" -n src tests; then
  echo "FAIL: mojibake detected"
  exit 1
fi

rm -rf .pytest_cache
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
find . -name "*.pyc" -delete

echo
echo "=== OK ==="
echo "All checks passed."
