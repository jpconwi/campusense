# Deploy NEMSAI on Streamlit Community Cloud

Put these files at the ROOT of your GitHub repo, next to `backend/` and `frontend/`:
- `streamlit_app.py`
- `requirements.txt`
- `.streamlit/secrets.toml.example`  (an example only - never commit real secrets)

Do NOT push `backend/.env`. Add it to `.gitignore`.

## 1. Google Cloud Console (your existing OAuth client)
Authorized redirect URI -> add: `https://YOUR-APP.streamlit.app/oauth2callback`
(Use the exact app URL Streamlit gives you. Save, wait a few minutes.)

## 2. Streamlit Cloud
1. share.streamlit.io -> Create app -> pick the repo, branch, main file `streamlit_app.py`.
2. Advanced settings -> Python 3.12 (or 3.11) -> paste your Secrets
   (copy `.streamlit/secrets.toml.example` and fill in your real values).
3. Deploy. The app uses the SAME PostgreSQL database as Render.

## Notes
- Needs the database to accept outside connections (Render Postgres: use the *External* URL).
- Image uploads in forms are left out; everything else (chat, forms, PDFs, records,
  admin dashboard, users, campus info) works. Rooms and announcements editing stay in the React admin.
- PDFs are generated per session; Streamlit Cloud's disk is temporary, so download them right away.
