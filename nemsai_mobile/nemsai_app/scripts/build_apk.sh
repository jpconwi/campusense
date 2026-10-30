#!/usr/bin/env bash
# Local build:  ./scripts/build_apk.sh   ->  build/NEMSAI.apk (signed with keystore/nemsai-release.jks if present)
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/setup_android.sh
flutter build apk --release
OUT=build/app/outputs/flutter-apk/app-release.apk
if [ -f keystore/nemsai-release.jks ]; then
  : "${KEYSTORE_PASSWORD:?set KEYSTORE_PASSWORD}" "${KEY_ALIAS:=nemsai}"
  APKSIGNER=$(ls "$ANDROID_HOME"/build-tools/*/apksigner | sort -V | tail -1)
  "$APKSIGNER" sign --ks keystore/nemsai-release.jks --ks-key-alias "$KEY_ALIAS" \
     --ks-pass env:KEYSTORE_PASSWORD --key-pass env:KEYSTORE_PASSWORD --out build/NEMSAI.apk "$OUT"
else
  echo "No keystore found - copying the debug-signed APK (Google sign-in will NOT work with it)."
  cp "$OUT" build/NEMSAI.apk
fi
echo "Built build/NEMSAI.apk"
