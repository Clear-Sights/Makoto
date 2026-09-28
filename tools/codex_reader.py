#!/usr/bin/env python3
"""A Codex reader for Scour's judgment layer (START step 14): the command Scour's
SCOUR_JUDGMENT_READER names. Scour appends `--model M` and writes the prompt on stdin; this runs
`codex exec` on that model in the working directory Scour gives (an empty temp dir), read-only,
and prints what Scour parses: {"result": the final answer, "usage": {...tokens}}.

Not fully sealed: Codex keeps its read-only shell. The prompt carries the whole unit, and the
directory is empty, so nothing in the tree under review is in reach.
usage (set by Scour): SCOUR_JUDGMENT_READER="python3 /path/tools/codex_reader.py [--effort E]"
"""
import json
import os
import subprocess
import sys
import tempfile


def main(argv):
    model = argv[argv.index("--model") + 1]
    effort = argv[argv.index("--effort") + 1] if "--effort" in argv else "high"
    out = tempfile.mktemp(suffix=".txt")
    p = subprocess.run(["codex", "exec", "--skip-git-repo-check", "--json", "-s", "read-only",
                        "-m", model, "-c", f"model_reasoning_effort={effort}", "-o", out, "-"],
                       input=sys.stdin.read(), capture_output=True, text=True, timeout=1500)
    used = {}
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        u = ev.get("usage") if isinstance(ev, dict) else None
        if isinstance(u, dict):
            for k, v in u.items():
                if isinstance(v, int):
                    used[k] = used.get(k, 0) + v
    result = open(out, encoding="utf-8").read() if os.path.exists(out) else ""
    print(json.dumps({"result": result.strip(), "usage": {
        "input_tokens": used.get("input_tokens", 0) - used.get("cached_input_tokens", 0),
        "cache_read_input_tokens": used.get("cached_input_tokens", 0),
        "output_tokens": used.get("output_tokens", 0)}, "rc": p.returncode}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
