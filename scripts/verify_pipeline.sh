#!/bin/bash
# Full pipeline verification (Phase 1, 3A, 3B-1) in the project .venv. Run from the project root:
#   mkdir -p tmp && bash scripts/verify_pipeline.sh > tmp/verify_pipeline.log 2>&1
# Optional: VENV=/path/to/other/venv bash scripts/verify_pipeline.sh
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p tmp
VENV="${VENV:-$PWD/.venv}"
source "$VENV/bin/activate"
echo "== python: $(which python) $(python --version 2>&1)"
python -c "import pandas, numpy; print('pandas', pandas.__version__, 'numpy', numpy.__version__)"
python -m pip --version 2>/dev/null || echo "pip: not available in this environment"
missing=$(python - <<'PY'
import importlib.util
mods = {"nbconvert": "nbconvert", "ipykernel": "ipykernel", "pytest": "pytest", "openpyxl": "openpyxl"}
print(" ".join(m for m in mods if importlib.util.find_spec(m) is None))
PY
)
if [ -n "$missing" ]; then
  echo "== installing requirements-dev (missing: $missing)"
  python -m pip install -q -r requirements-dev.txt || { echo "PIP_FAILED"; exit 1; }
fi
python -m ipykernel install --prefix "$VENV" --name ecommerce-venv --display-name "Python (ecommerce .venv)" >/dev/null && echo "== kernel ecommerce-venv registered in $VENV"
python -m jupyter kernelspec list | grep ecommerce-venv
python -c "import json;print('kernel argv:', json.load(open('$VENV/share/jupyter/kernels/ecommerce-venv/kernel.json'))['argv'][0])"
export PYTHONDONTWRITEBYTECODE=1
status=0
echo "== layout check"
extra=$(ls notebooks/*.ipynb | grep -v -E "notebooks/0[1-5]_[a-z_]+\.ipynb$" || true)
if [ -n "$extra" ]; then echo "LAYOUT_FAILED unexpected notebooks (close them in your editor and move them to archive/): $extra"; exit 1; fi
echo "== validate"
python scripts/validate_input_data.py --input "data/raw/Online Retail.xlsx" --mapping config/schema_mapping_template.csv --output outputs/data_quality_precheck.csv | tail -2 || status=1
echo "== standardize"
python scripts/standardize_raw_sales.py --input "data/raw/Online Retail.xlsx" --mapping config/schema_mapping_template.csv --output data/interim/standardized_sales.csv | tail -2 || status=1
for nb in notebooks/01_data_cleaning.ipynb notebooks/02_sql_business_queries.ipynb notebooks/03_sku_classification.ipynb notebooks/04_replenishment_warehouse_allocation.ipynb notebooks/05_working_capital_impact.ipynb; do
  echo "== execute $nb"
  python -m jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=ecommerce-venv --ExecutePreprocessor.timeout=600 "$nb" > tmp/nbconvert_last.log 2>&1
  rc=$?
  tail -3 tmp/nbconvert_last.log
  [ "$rc" -eq 0 ] || { echo "NOTEBOOK_FAILED $nb (exit $rc)"; status=1; }
done
echo "== compare: phase 1 (original -> end of phase 1, snapshots)"
python scripts/compare_to_baseline.py --baseline reports/baseline_before_phase1 --current reports/baseline_end_phase1 --prefix phase1 > /dev/null || status=1
echo "== compare: phase 3A (end of phase 1 -> end of phase 3A, snapshots)"
python scripts/compare_to_baseline.py --baseline reports/baseline_end_phase1 --current reports/baseline_end_phase3a --prefix phase3a > /dev/null || status=1
echo "== compare: phase 3B-1 (end of phase 3A -> live)"
python scripts/compare_to_baseline.py --baseline reports/baseline_end_phase3a --current live --prefix phase3b1 || status=1
echo "== attribution of model changes"
python scripts/attribute_model_changes.py --output reports/phase3b1_attribution.csv || status=1
echo "== simulation stability"
python scripts/check_simulation_stability.py --output reports/phase3b1_simulation_stability.csv || status=1
echo "== pytest -W error"
python -m pytest -W error -p no:cacheprovider || status=1
echo "== revenue check"
python - <<'PY' || status=1
import pandas as pd
s = pd.read_csv("data/processed/clean_sales.csv", usecols=["revenue"])
print(f"revenue {s['revenue'].sum():,.2f}")
PY
echo "== DONE status=$status"

exit "$status"
