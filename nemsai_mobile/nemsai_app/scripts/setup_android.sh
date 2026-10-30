#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d android ] || flutter create --platforms=android --org ph.edu.nemsu --project-name nemsai .
rm -f test/widget_test.dart
python3 android_overrides/patch_manifest.py
flutter pub get
dart run flutter_launcher_icons