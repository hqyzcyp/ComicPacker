#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 2:
        return 0

    hook_event_name = sys.argv[1].strip()
    context = sys.stdin.read()
    if not context.strip():
        return 0

    payload = {
        "hookSpecificOutput": {
            "hookEventName": hook_event_name,
            "additionalContext": context,
        }
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
