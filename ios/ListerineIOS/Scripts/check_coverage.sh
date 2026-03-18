#!/usr/bin/env bash
set -euo pipefail

package_dir=$(cd "$(dirname "$0")/.." && pwd)
cd "$package_dir"

swift test --enable-code-coverage

profdata=$(find .build -name default.profdata | head -n 1)
if [[ -z "$profdata" ]]; then
  echo "Coverage data not found" >&2
  exit 1
fi

binary=$(find .build -path '*/debug/ListerineIOSPackageTests.xctest' -type f | head -n 1)
if [[ -z "$binary" ]]; then
  binary=$(find .build -path '*/debug/ListerineCorePackageTests.xctest' -type f | head -n 1)
fi
if [[ -z "$binary" ]]; then
  echo "Swift test bundle not found" >&2
  exit 1
fi

coverage_json=$(mktemp)
llvm-cov export "$binary" -instr-profile "$profdata" > "$coverage_json"

python - <<'PY' "$coverage_json"
import json
import pathlib
import sys

coverage_path = pathlib.Path(sys.argv[1])
report = json.loads(coverage_path.read_text())
source_marker = "/Sources/ListerineCore/"
covered = 0
count = 0
for entry in report["data"][0]["files"]:
    if source_marker in entry["filename"]:
        lines = entry["summary"]["lines"]
        covered += lines["covered"]
        count += lines["count"]
coverage = 100.0 if count == 0 else covered * 100.0 / count
print(f"Swift ListerineCore coverage: {coverage:.2f}% ({covered}/{count} lines)")
threshold = 99.0
if coverage + 1e-9 < threshold:
    raise SystemExit(f"Coverage {coverage:.2f}% is below required threshold {threshold:.2f}%")
PY

rm -f "$coverage_json"
