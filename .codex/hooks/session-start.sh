#!/bin/sh
# project-local: SessionStart hook for Codex
# Runs session catchup and planning context, then emits valid Codex hook JSON.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
CODEX_ROOT="$HOME/.codex"
SKILL_DIR="$CODEX_ROOT/skills/planning-with-files"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

[ -n "$PYTHON_BIN" ] || exit 0

TMP_FILE="$(mktemp)"
cleanup() {
    rm -f "$TMP_FILE"
}
trap cleanup EXIT INT TERM

if [ -f "$SKILL_DIR/scripts/session-catchup.py" ]; then
    catchup_output="$($PYTHON_BIN "$SKILL_DIR/scripts/session-catchup.py" "$(pwd)" 2>/dev/null || true)"
    if [ -n "$catchup_output" ]; then
        printf '[planning-with-files] Session catchup:\n%s\n\n' "$catchup_output" >> "$TMP_FILE"
    fi
fi

if [ -f "$SCRIPT_DIR/planning-context.sh" ]; then
    sh "$SCRIPT_DIR/planning-context.sh" >> "$TMP_FILE"
fi

[ -s "$TMP_FILE" ] || exit 0

"$PYTHON_BIN" "$SCRIPT_DIR/emit_context_hook.py" "SessionStart" < "$TMP_FILE"
exit 0
