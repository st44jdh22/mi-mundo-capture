#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if ! command -v xcodebuild >/dev/null || ! command -v xcrun >/dev/null; then
  echo 'BLOCKED: macOS/Xcode/iOS simulator required. No Swift or XCTest result produced.' >&2
  exit 2
fi
if [ "$#" -lt 1 ]; then
  echo 'Usage: ios/checks/run_simulator.sh SIMULATOR_UUID [--dat]' >&2
  xcodebuild -showdestinations -project ios/HeySophie.xcodeproj -scheme HeySophie
  exit 2
fi
xcodebuild -version
xcrun swift --version
xcrun simctl list devices available
if [ "${2:-}" = '--dat' ]; then
  python3 ios/generate_project.py --dat
  trap 'python3 ios/generate_project.py' EXIT
else
  python3 ios/generate_project.py
fi
# Ad-hoc simulator signing supplies the application identity needed by DAT keychain.
# No Apple account, development team or provisioning profile is used.
xcodebuild -project ios/HeySophie.xcodeproj -scheme HeySophie \
  -destination "platform=iOS Simulator,id=$1" \
  -derivedDataPath "${HS_META_DERIVED_DATA_PATH:-ios/DerivedData}" -parallel-testing-enabled NO -collect-test-diagnostics never \
  CODE_SIGNING_ALLOWED=YES CODE_SIGN_IDENTITY=- DEVELOPMENT_TEAM= test
