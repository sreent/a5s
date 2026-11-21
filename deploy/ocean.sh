#!/bin/sh
# Take Ocean, the look a5s shares with a7c and a3t, from its one source, sreent/ocean, at one of
# its commits (docs/design.md): its tokens, its pieces, its chart colours and its fonts, copied
# into src/a5s/core/webchat/ocean as they are there, with the commit and each file's digest in
# ocean.json. a5s's pages load only a5s's own files, so a5s serves a copy rather than load Ocean
# from anywhere, and tests/test_design.py holds the copy to the digests: a change to Ocean is
# made in sreent/ocean, and taken here with this.
#
#   sh deploy/ocean.sh <commit>
set -eu
if ! python3 -c '' >/dev/null 2>&1; then
  python3() { uv run python "$@"; }
fi
commit=${1:?name the commit of sreent/ocean to take, such as its latest on main}
here=$(cd "$(dirname "$0")/.." && pwd)
into="$here/src/a5s/core/webchat/ocean"
there=$(mktemp -d)
trap 'rm -rf "$there"' EXIT

git init -q "$there"
git -C "$there" fetch -q --depth 1 https://github.com/sreent/ocean "$commit"
git -C "$there" checkout -q FETCH_HEAD
taken=$(git -C "$there" rev-parse HEAD)

rm -rf "$into/css" "$into/fonts"
mkdir -p "$into/css" "$into/fonts"
cp "$there/css/tokens.css" "$there/css/components.css" "$there/css/charts.css" "$into/css/"
cp "$there"/fonts/*.woff2 "$there"/fonts/OFL-*.txt "$into/fonts/"

python3 - "$into" "$taken" <<'PY'
import hashlib, json, sys
from pathlib import Path
into, commit = Path(sys.argv[1]), sys.argv[2]
files = {p.relative_to(into).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(into.rglob("*")) if p.is_file() and p.name != "ocean.json"}
(into / "ocean.json").write_text(json.dumps(
    {"repository": "https://github.com/sreent/ocean", "commit": commit, "files": files},
    indent=2) + "\n")
PY
echo "took Ocean at $taken into $into"
