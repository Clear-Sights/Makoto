#!/usr/bin/env bash
python3 "${CLAUDE_PLUGIN_ROOT}/skill_triggers/hooks/trigger.py" SessionStart 2>/dev/null || true
