#!/usr/bin/env bash
# Generates the android/ folder (needs Flutter installed) and applies the app's settings.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d android ] || flutter create --platforms=android --org ph.edu.nemsu --project-name nemsai .
python3 android_overrides/patch_manifest.py
flutter pub get
dart run flutter_launcher_icons
