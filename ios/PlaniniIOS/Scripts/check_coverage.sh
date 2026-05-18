#!/usr/bin/env bash
set -euo pipefail

package_dir=$(cd "$(dirname "$0")/.." && pwd)
cd "$package_dir"

swift test --quiet --enable-code-coverage

profdata=$(find .build -name default.profdata | head -n 1)
if [[ -z "$profdata" ]]; then
  echo "Coverage data not found" >&2
  exit 1
fi

binary=$(find .build -path '*/debug/PlaniniIOSPackageTests.xctest' -type f | head -n 1)
if [[ -z "$binary" ]]; then
  bundle=$(find .build -path '*/debug/PlaniniIOSPackageTests.xctest' -type d | head -n 1)
  if [[ -n "$bundle" && -x "$bundle/Contents/MacOS/PlaniniIOSPackageTests" ]]; then
    binary="$bundle/Contents/MacOS/PlaniniIOSPackageTests"
  fi
fi
if [[ -z "$binary" ]]; then
  binary=$(find .build -path '*/debug/PlaniniCorePackageTests.xctest' -type f | head -n 1)
fi
if [[ -z "$binary" ]]; then
  bundle=$(find .build -path '*/debug/PlaniniCorePackageTests.xctest' -type d | head -n 1)
  if [[ -n "$bundle" && -x "$bundle/Contents/MacOS/PlaniniCorePackageTests" ]]; then
    binary="$bundle/Contents/MacOS/PlaniniCorePackageTests"
  fi
fi
if [[ -z "$binary" ]]; then
  echo "Swift test bundle not found" >&2
  exit 1
fi
if [[ -d "$binary" ]]; then
  executable_name=$(basename "$binary" .xctest)
  binary="$binary/Contents/MacOS/$executable_name"
fi
if [[ ! -f "$binary" ]]; then
  echo "Swift test executable not found" >&2
  exit 1
fi

coverage_json=$(mktemp)
coverage_script=$(mktemp)
llvm_cov=(llvm-cov)
if ! command -v llvm-cov >/dev/null 2>&1; then
  llvm_cov=(xcrun llvm-cov)
fi
"${llvm_cov[@]}" export "$binary" -instr-profile "$profdata" > "$coverage_json"

cat > "$coverage_script" <<'SWIFT'
import Foundation

let coveragePath = URL(fileURLWithPath: CommandLine.arguments[1])
let data = try Data(contentsOf: coveragePath)
let json = try JSONSerialization.jsonObject(with: data) as! [String: Any]
let report = (json["data"] as! [[String: Any]])[0]
let files = report["files"] as! [[String: Any]]
let sourceMarker = "/Sources/PlaniniCore/"

var covered = 0
var count = 0
for entry in files where (entry["filename"] as? String)?.contains(sourceMarker) == true {
    let summary = entry["summary"] as! [String: Any]
    let lines = summary["lines"] as! [String: Any]
    covered += lines["covered"] as! Int
    count += lines["count"] as! Int
}

let coverage = count == 0 ? 100.0 : (Double(covered) * 100.0 / Double(count))
print(String(format: "Swift PlaniniCore coverage: %.2f%% (%d/%d lines)", coverage, covered, count))
let threshold = 99.0
if coverage + 1e-9 < threshold {
    fputs(String(format: "Coverage %.2f%% is below required threshold %.2f%%\n", coverage, threshold), stderr)
    exit(1)
}
SWIFT

swift "$coverage_script" "$coverage_json"

rm -f "$coverage_json" "$coverage_script"
