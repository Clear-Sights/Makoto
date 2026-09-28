#!/bin/sh
# Launch row: Scour at its pin, run over this tree with the register at its pin.
# Exit 0: Scour printed its verdict line (its findings are the work list, in the detail file).
# Any other exit: stop and report the printed LAUNCH MISSING line.
SCOUR_PIN=45cd655
REGISTER_PIN=c544c4e
here=$(cd "$(dirname "$0")/.." && pwd)
name=$(basename "$here")
missing() { echo "LAUNCH MISSING scour: $1"; exit 2; }
s=$(ls -d "$here/../Scour" "$here/../scour" 2>/dev/null | head -1)
m=$(ls -d "$here/../Measure-Zero" "$here/../measure-zero" 2>/dev/null | head -1)
[ -n "$s" ] || missing "attach Clear-Sights/Scour with add_repo and clone it beside this repository"
[ -n "$m" ] || missing "attach Clear-Sights/Measure-Zero with add_repo and clone it beside this repository (it holds the register)"
git -C "$s" cat-file -e "$SCOUR_PIN^{commit}" 2>/dev/null || missing "run git -C $s fetch origin $SCOUR_PIN"
git -C "$m" cat-file -e "$REGISTER_PIN^{commit}" 2>/dev/null || missing "run git -C $m fetch origin $REGISTER_PIN"
d=$(mktemp -d)
git -C "$s" archive "$SCOUR_PIN" | tar -x -C "$d" || missing "Scour $SCOUR_PIN did not extract"
git -C "$m" show "$REGISTER_PIN:zero/resources/REGISTER.md" > "$d/REGISTER.md" || missing "the register at $REGISTER_PIN did not read"
detail="${TMPDIR:-/tmp}/scour-$name.txt"
out=$(cd "$d" && python3 -m scour "$here" --register "$d/REGISTER.md" --detail "$detail")
rc=$?
echo "$out"
# exit 1 is findings, the work list; only a refusal (2) or no verdict line is red at launch
[ "$rc" -le 1 ] && echo "$out" | grep -q '^SCOUR entries=' || missing "Scour refused this tree (exit $rc); read $detail"
echo "scour detail: $detail"
