#!/usr/bin/env bash
# Local operator entrypoint for Aplikuj IT-category-v2. Never auto-starts a crawl.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
OUT="$ROOT/.local-crawl/scale-04-it-v2"
RAW="$ROOT/.local-evidence/scale-04-it-v2"
INV="$OUT/inventory"
PLAN="$INV/chunks.json"
STATUS="$OUT/status.json"
LOG="$OUT/crawler.log"
SESSION="aplikuj-it-v2"

running() { tmux has-session -t "$SESSION" 2>/dev/null; }
require_plan() {
    [[ -s "$PLAN" ]] || { echo "Brak planu v2. Najpierw: bash scripts/aplikuj_v2.sh prepare" >&2; exit 2; }
    "$PY" -c 'import json,sys; p=json.load(open(sys.argv[1])); assert p.get("aplikuj_scope")=="it-category-v2", "Niepoprawny plan Aplikuj"' "$PLAN"
}
case "${1:-help}" in
    prepare)
        if running; then echo "Crawler działa; nie przebudowuj jego planu." >&2; exit 2; fi
        if [[ -e "$PLAN" ]]; then
            echo "Plan już istnieje: $PLAN. Nie przebudowuję identyfikatorów/chunków w aktywnym przebiegu." >&2
            exit 2
        fi
        if [[ -d "$OUT/aplikuj" ]] && find "$OUT/aplikuj" -name manifest.json -print -quit | grep -q .; then
            echo "Są już paczki w $OUT, ale nie ma planu. Odmawiam mieszania przebiegów." >&2; exit 2
        fi
        mkdir -p "$INV"
        "$PY" -m ingestion.build_scale04_inventory --sources aplikuj --out "$INV"
        "$PY" -m ingestion.plan_inventory_chunks --inventory "$INV/inventory.jsonl.gz" --out "$PLAN" --chunk-size 50
        echo "Plan gotowy: $PLAN. Start: bash scripts/aplikuj_v2.sh start"
        ;;
    start)
        require_plan
        if running; then echo "Crawler już działa w tmux: $SESSION"; exit 2; fi
        mkdir -p "$OUT" "$RAW"
        tmux new-session -d -s "$SESSION" "exec '$PY' -u -m ingestion.run_file_backed_plan --plan '$PLAN' --sources aplikuj --out-root '$OUT' --raw-root '$RAW' --status '$STATUS' >> '$LOG' 2>&1"
        echo "Uruchomiono: $SESSION. Log: $LOG"
        ;;
    status)
        if running; then echo "PROCESS: RUNNING ($SESSION)"; else echo "PROCESS: STOPPED (could be completed or paused; check log/status)"; fi
        if [[ -f "$STATUS" ]]; then
            jq '{updated_at, aplikuj: .sources.aplikuj, total: .total}' "$STATUS"
        else
            echo "Brak pliku statusu; crawler v2 jeszcze nie uruchomiony."
        fi
        ;;
    watch)
        [[ -f "$STATUS" ]] || { echo "Brak status.json; najpierw start." >&2; exit 2; }
        watch -n 5 "jq '{updated_at, aplikuj: .sources.aplikuj, total: .total}' '$STATUS'"
        ;;
    logs)
        [[ -f "$LOG" ]] || { echo "Brak logu; najpierw start." >&2; exit 2; }
        tail -n 50 -f "$LOG"
        ;;
    verify)
        "$PY" -m ingestion.verify_aplikuj_v2 --root "$OUT"
        ;;
    stop)
        if running; then
            tmux send-keys -t "$SESSION" C-c
            echo "Wysłano SIGINT do crawlera; sprawdź status i logi."
        else
            echo "Brak aktywnej sesji $SESSION"
        fi
        ;;
    help|*)
        echo "Użycie: bash scripts/aplikuj_v2.sh {prepare|start|status|watch|logs|verify|stop}"
        echo "prepare tworzy niezmienny indeks i plan; start uruchamia w tmux; stop przerywa bez kasowania archiwum."
        ;;
esac
