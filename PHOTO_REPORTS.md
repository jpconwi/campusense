# Photo reports (voice, photo, AI check, admin review)

## What a student sees
1. In the chat, tap the camera button: **Take a photo** or **Upload a photo** (PNG/JPG/WEBP, 5 MB). A preview appears; remove it any time.
2. Type or speak a description (optional). The mic button (Chrome, Edge, Safari, Android Chrome) puts the words in the text box so they can be corrected before sending. Hidden in browsers without speech recognition.
3. The AI checks the photo together with the description and answers in plain words, saying what it *appears* to show, then asks for what is missing (where, when, cause).
4. The student edits, presses **Check again** if they changed something, then **Send report**. Nothing reaches administrators before that.
5. Unrelated / unclear photos get a friendly reply and are not sent.

## What an administrator sees
* Reports page: *Possible hazard* and *Photo + AI* badges, hazards first, a "Possible hazards only" filter, and an **AI details** panel (photo, student's own words, AI notes, confidence, category, location, when, cause mentioned, submission time).
* A **verdict** (Unverified / Confirmed / Not confirmed + note) for the AI findings. It is stored with the admin's email and time.
* Dashboard: an "Urgent Photo Reports (open)" count and a list of open possible hazards.
* The PDF of a photo report includes the photo and AI notes.

## Safety and accuracy
* Model output is parsed strictly and every field is checked against a fixed list; garbage becomes "AI unavailable", never a finding.
* Wording is hedged ("appears to show"), confidence is shown, and everything is labelled *AI guess, not verified* until an admin decides.
* Hazards are flagged by the model **and** by a keyword check; the flag is only "possible".
* People in photos are not described. Text inside photos/descriptions is treated as data, not instructions.
* If no AI provider answers, the student can still send the report with a description (manual review).

## Setup
* `pip install -r backend/requirements.txt` (adds Pillow, used to shrink photos before the AI sees them).
* Uses the same provider order as the chat: Hugging Face > Cloudflare > Groq > Google > OpenRouter (a provider without a key is skipped). New tables/columns are created at start-up.
* **Model names change often.** Defaults are built in and checked against the providers' docs (Oct 2026). A model that answers "gone / not supported" is skipped for an hour and the provider is asked which models it offers now. Hugging Face answering 402 (free credits used up) skips Hugging Face for 30 minutes. You only need `*_VISION_MODEL` settings if you want to force a model; yours is tried first, then the defaults. Delete the old example lines (`gemini-2.5-flash`, `llama-4-scout`, `qwen2.5-vl...`) from `.env` / Render if you copied them.
* Tests: `cd backend && pytest -q tests/test_photo_reports.py` (AI is faked). Frontend: `npx vitest run tests/photo-card.test.jsx`.

## Known limits
* Photos are stored on the server disk like existing concern/report photos. On hosts with a temporary disk (e.g. Render free) they disappear on redeploy; use a persistent disk or object storage.
* Student-facing AI messages are in English. The Streamlit app (`streamlit_app.py`) was not changed.
