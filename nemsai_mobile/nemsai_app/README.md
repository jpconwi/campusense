# NEMSAI - Flutter app (student + instructor)

The same Flutter app targets Android and iOS. Android build instructions are below; the iOS build is configured in the repository-root `codemagic.yaml`.

Native Android port of the NEMSAI website: sign-in, personal-Gmail registration (with built-in ID / COR scanner),
student + instructor dashboard, Campus AI chat (with photo reports), concerns, reports, feedback,
reservations and faculty availability. Backend: https://nemsu-ai-backend.onrender.com

Not included: the admin dashboard (admins see a "use the website" screen) and voice dictation.

## 1. Backend change (required for registration)
Replace `backend/app/routers/mobile_auth.py` with `backend_patch/mobile_auth.py` and redeploy on Render.
It only adds things: `purpose: "register"` on the existing mobile login, plus
`POST /api/auth/mobile/register/student` and `/instructor`. The website is untouched.
Without it, NEMSU-email login works but personal-Gmail registration will not.

## 2. Google Cloud (required for Google sign-in)
In the same project as the website's OAuth client, create an **Android** OAuth client:
- Package name: `ph.edu.nemsu.nemsai`
- SHA-1: `62:29:EE:69:B8:C7:74:E0:53:F9:8D:A9:28:08:EF:A1:FD:D0:14:45`  (this is the key in `signing_key/`)
Keep the existing **Web** client; the app already uses its ID (it must equal GOOGLE_CLIENT_ID on the backend).

## 3. Build the APK (GitHub Actions - no local setup)
1. Push this folder to a GitHub repo (branch `main`).
2. Repo > Settings > Secrets > Actions, add `KEYSTORE_BASE64` (contents of signing_key/keystore_base64.txt),
   `KEYSTORE_PASSWORD` and `KEY_ALIAS` (values in signing_key/github_secrets.txt).
3. Actions > "Build Android APK" > Run workflow. Download **NEMSAI-apk** > `NEMSAI.apk`.
Local alternative: install Flutter 3.27.x + Android SDK, set KEYSTORE_PASSWORD, run `./scripts/build_apk.sh`.

## 4. Install on phones
Send NEMSAI.apk to the phone, open it, allow "install unknown apps". Back up the signing key: if it is lost,
future updates cannot replace the installed app and Google sign-in must be re-registered.

## 5. iOS build with Codemagic

1. Push the repository to GitHub and connect it to a personal Codemagic account. The workflow uses the root `codemagic.yaml` and builds the Flutter app from `nemsai_mobile/nemsai_app`. Codemagic currently gives personal accounts 500 macOS M2 build minutes per month.
2. In Google Cloud, create an **iOS OAuth client** with bundle ID `ph.edu.nemsu.nemsai`. Keep the existing Web OAuth client above. Add the iOS client ID to Codemagic as the environment variable `GOOGLE_IOS_CLIENT_ID`.
3. Run the `ios-free-build` workflow. It produces an **unsigned IPA** artifact for inspection or later signing.

### Installing on an iPhone

An unsigned IPA from Codemagic cannot be installed directly on an iPhone. Apple requires an iOS development or distribution signature. A free Apple Account can install a personal test build through Xcode on a Mac, but its provisioning expires after 7 days and the app must be rebuilt and reinstalled. Codemagic's standard signed device distribution and TestFlight/App Store publishing require Apple Developer Program signing; membership is USD 99/year (regional pricing may differ). Therefore, free Codemagic builds are possible, but persistent installation for other users at zero cost is not an Apple-supported path.

For a zero-cost personal test, use a Mac with Xcode: open `ios/Runner.xcworkspace`, select the Runner target, set your Apple Account under **Signing & Capabilities**, select your iPhone, then build and run. Keep the bundle ID unique if another developer account already uses it. For broader iPhone distribution, enroll in Apple Developer Program and add signing to the Codemagic workflow.

Sources: [Codemagic pricing](https://docs.codemagic.io/billing/pricing/), [Apple account capabilities and 7-day personal provisioning](https://developer.apple.com/help/account/basics/about-your-developer-account), [Apple Developer Program pricing](https://developer.apple.com/programs/enroll/).

## Scanner
Scan with camera: full-screen camera with a frame; it watches the live preview and auto-captures after ~1.3 s of a
steady, sharp, lit document, crops to the frame, then checks quality. A manual shutter and torch are always there.
If the camera is missing/broken/denied, the slot falls back to Upload only. Thresholds are in
`lib/util/frame_analyzer.dart` (class Tuning) - adjust after trying real IDs.

## Notes
- Render's free tier sleeps: the first request can take ~1 min; the app shows skeletons and a "waking up" banner.
- Change the server with `--dart-define=API_BASE=...`.
