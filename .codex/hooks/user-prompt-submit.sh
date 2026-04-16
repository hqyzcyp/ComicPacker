#!/bin/sh
# project-local: User prompt submit hook for Codex
# Emit valid Codex hook JSON instead of raw text.

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

[ -n "$PYTHON_BIN" ] || exit 0
[ -f "$SCRIPT_DIR/planning-context.sh" ] || exit 0

context="$(sh "$SCRIPT_DIR/planning-context.sh")"
[ -n "$context" ] || exit 0

printf '%s\n' "$context" | "$PYTHON_BIN" "$SCRIPT_DIR/emit_context_hook.py" "UserPromptSubmit"
exit 0
