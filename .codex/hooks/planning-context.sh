#!/bin/sh
# project-local: shared plain-text planning context generator

if [ -f task_plan.md ]; then
    echo "[planning-with-files] ACTIVE PLAN — current state:"
    head -50 task_plan.md
    echo ""
    echo "=== recent progress ==="
    tail -20 progress.md 2>/dev/null || true
    echo ""
    echo "[planning-with-files] Read findings.md for research context. Continue from the current phase."
fi
