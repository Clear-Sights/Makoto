#!/usr/bin/env bash
python3 "${CLAUDE_PLUGIN_ROOT}/skill_triggers/hooks/trigger.py" PreToolUse 2>/dev/null || true
