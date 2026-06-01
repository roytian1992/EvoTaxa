#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/vepfs-mlp2/c20250513/241404044/users/roytian/EvoTaxa"
RUN_ROOT="data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/run_output"
OUT_ROOT="data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/successor_schema_group_full_24w_20260531"
CONFIG="data/schema_probe/css_screened_20260530_v2/mainflow_proposal/successor_edge_full_4126_20260530/config.qwen235_successor_full_4126.json"
LOG_ROOT="data/schema_probe/css_screened_20260530_v2/mainflow_proposal/full_llm_nodes_4126_20260530/logs"
LLM_LOG="${LOG_ROOT}/successor_schema_group_full_24w_20260531.log"
PIPELINE_LOG="${LOG_ROOT}/successor_schema_group_full_pipeline_20260531.log"
TOTAL_CANDIDATES=39182

cd "$REPO_ROOT"
source ../anaconda3/bin/activate
export EVOTAXA_LLM_API_KEY="${EVOTAXA_LLM_API_KEY:?Set EVOTAXA_LLM_API_KEY before running this pipeline}"
export PYTHONPATH="scripts:src"
mkdir -p "$LOG_ROOT" "$OUT_ROOT"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$PIPELINE_LOG"
}

decision_count() {
  if [[ -f "${OUT_ROOT}/successor_decisions.jsonl" ]]; then
    wc -l < "${OUT_ROOT}/successor_decisions.jsonl"
  else
    printf '0\n'
  fi
}

extract_running() {
  pgrep -f "extract_successor_edges.py .*${OUT_ROOT}" >/dev/null 2>&1
}

run_extract_resume() {
  log "Starting/resuming schema-group successor LLM judging."
  python scripts/extract_successor_edges.py \
    --config "$CONFIG" \
    --run-root "$RUN_ROOT" \
    --output-root "$OUT_ROOT" \
    --candidate-limit 0 \
    --llm-limit "$TOTAL_CANDIDATES" \
    --candidate-scope schema_group \
    --batch-size 4 \
    --workers 24 \
    --max-sources-per-target 120 \
    --per-target-candidates 6 \
    --run-llm \
    --resume \
    --retry-failed-decisions >> "$LLM_LOG" 2>&1
}

log "Pipeline watcher started."
while [[ "$(decision_count)" -lt "$TOTAL_CANDIDATES" ]]; do
  current="$(decision_count)"
  if extract_running; then
    log "LLM judging is running: ${current}/${TOTAL_CANDIDATES} decisions."
    sleep 300
  else
    log "LLM judging not running and incomplete: ${current}/${TOTAL_CANDIDATES}; resuming."
    run_extract_resume
    sleep 10
  fi
done

log "LLM decisions complete: $(decision_count)/${TOTAL_CANDIDATES}. Running one failed-decision retry pass."
run_extract_resume

log "Applying strict successor-edge display filter and installing edges."
python scripts/filter_successor_edges.py \
  --input-root "$OUT_ROOT" \
  --output-root "${OUT_ROOT}/strict_final" \
  --run-root "$RUN_ROOT" \
  --min-confidence 0.84 \
  --min-time-delta-days 180 \
  --install >> "$PIPELINE_LOG" 2>&1

log "Materializing entity cards and successor trajectories."
python scripts/materialize_evolution_artifacts.py \
  --run-root "$RUN_ROOT" \
  --support-doc-limit 24 \
  --mention-limit 24 \
  --edge-limit 24 >> "$PIPELINE_LOG" 2>&1

log "Rebuilding dashboard artifacts."
python scripts/build_evolution_visualization.py \
  --run-root "$RUN_ROOT" \
  --max-nodes 1600 \
  --max-edges 1200 \
  --max-trajectories 1000 \
  --max-windows 400 \
  --support-doc-limit 12 >> "$PIPELINE_LOG" 2>&1

log "Restarting dashboard server."
tmux kill-session -t evotaxa_dashboard 2>/dev/null || true
tmux new-session -d -s evotaxa_dashboard \
  "cd $REPO_ROOT && source ../anaconda3/bin/activate && python scripts/serve_evolution_dashboard.py --run-root $RUN_ROOT --port 8765 --max-nodes 1600 --max-edges 1200 --max-trajectories 1000 --max-windows 400 > ${RUN_ROOT}/visualization/logs/dashboard_server.log 2>&1"

log "Schema-group successor full pipeline complete."
