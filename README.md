# CampusSense AI - NEMSU Tandag Main Campus

Campus assistant and reporting platform: **Google sign-in (NEMSU accounts only)**, student /
instructor / admin roles, AI chat, faculty availability, concerns, reports, feedback,
reservations, PDF reports and an admin dashboard.

**Stack:** FastAPI (Python) + React (Vite) + PostgreSQL.
This is the same app as the earlier Flask + Jinja + SQLite/CSV version, with the same features,
rules and look.

---------------------------------------------------------------------

## 1. Folder structure

```
CampusSenseAi/
├── docker-compose.yml           Optional PostgreSQL for development
├── backend/                     FastAPI - everything on the server
│   ├── app/
│   │   ├── main.py              Starts the app (sessions, error JSON, serves the React build)
│   │   ├── config.py            All settings; reads backend/.env
│   │   ├── database.py          PostgreSQL connection (SQLAlchemy) + create tables on start
│   │   ├── models.py            The tables (see section 6)
│   │   ├── security.py          Who is logged in, role checks, CSRF
│   │   ├── routers/
│   │   │   ├── auth.py          Continue with Google, /me, role selection, logout
│   │   │   ├── admin_login.py   Admin email + password at the secret address
│   │   │   ├── api.py           Chat, forms, "my" lists, private PDF/image downloads
│   │   │   └── admin.py         Admin dashboard API (404 unless signed in as admin)
│   │   ├── services/            Business logic (one file per topic, same as before)
│   │   ├── ai/                  The "brain": intent.py (rules), ai_engine.py, context.py, response.py
│   │   ├── prompts/             Text instructions for the AI
│   │   └── model/systemAi.py    The ONLY file that talks to Hugging Face
│   ├── seed/campus_info.csv     Starter campus facts, loaded into the database on first start
│   ├── scripts/                 create_admin.py, import_legacy.py, make_test_users.py
│   ├── tests/                   pytest (runs against a real PostgreSQL)
│   ├── reports/                 Generated PDFs (private)
│   ├── uploads/                 Optional photos (private - never served publicly)
│   ├── requirements.txt
│   └── .env.example             Copy to .env
└── frontend/                    React app (Vite)
    ├── index.html
    ├── vite.config.js           Dev server forwards /api to FastAPI
    ├── public/logo.png
    ├── src/
    │   ├── main.jsx, App.jsx    Entry + all routes (and who may open them)
    │   ├── api.js               The only place that calls the backend (adds the CSRF header)
    │   ├── auth.jsx             Signed-in user, nav, flash messages
    │   ├── app.css              Same styles as before
    │   ├── components/          RecordForm (all 5 forms), Charts (SVG), Layout
    │   └── pages/               Login, RoleSelect, Chat, Home, MyList, Faculty, Profile,
    │                            AdminLogin, AdminDashboard, AdminList, AdminUsers,
    │                            AdminFaculty, AdminDataset
    └── tests/smoke.test.jsx     Renders the real React app against the running backend
```

**Where did the old files go?**

| Old (Flask) | New |
|---|---|
| `main.py`, `routes/api.py`, `routes/pages.py`, `auth/google_auth.py`, `admin/*.py` | `backend/app/main.py` + `backend/app/routers/*` |
| `templates/*.html`, `static/js/*.js` | `frontend/src/pages/*.jsx`, `components/*.jsx` |
| `static/css/app.css`, `static/logo.png` | `frontend/src/app.css`, `frontend/public/logo.png` |
| `database/database.py` (SQLite) | `backend/app/database.py` + `models.py` (PostgreSQL) |
| `data/faculty/faculty_availability.csv` | table `faculty_reports` |
| `data/rooms/rooms.csv` | table `rooms` |
| `data/campus/campus_info.csv` | table `campus_info` (seeded from `backend/seed/campus_info.csv`) |
| `services/`, `ai/`, `prompts/`, `model/` | `backend/app/services/`, `ai/`, `prompts/`, `model/` (same logic) |
| `create_admin.py` | `python -m scripts.create_admin` |
| `tests/run_checks.py` | `backend/tests/` (pytest) + `frontend/tests/smoke.test.jsx` |
| old `views/`, `dataset/`, root `faculty_availability.py`, `controller/` | removed (already replaced in the Flask version) |

---------------------------------------------------------------------

## 2. Setup

You need **Python 3.11+**, **Node 20+** and **PostgreSQL 14+**.

### PostgreSQL

Easiest with Docker: `docker compose up -d` (creates database `campusense` and `campusense_test`,
user `campus`, password `campus`).

Without Docker, in `psql` as the postgres user:

```sql
CREATE USER campus WITH PASSWORD 'campus';
CREATE DATABASE campusense OWNER campus;
CREATE DATABASE campusense_test OWNER campus;   -- only needed to run the tests
```

The tables are created automatically when the backend starts.

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Open `backend/.env` and fill it in (keep your existing `MODEL` and `API_KEY`):

```
DATABASE_URL=postgresql://campus:campus@localhost:5432/campusense
MODEL=...
API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
PUBLIC_URL=http://localhost:8000
SECRET_KEY=...
ADMIN_EMAILS=admin@nemsu.edu.ph
ADMIN_PASSWORD=...
```

Make a SECRET_KEY: `python -c "import secrets; print(secrets.token_hex(32))"`

### Frontend

```bash
cd frontend
npm install
```

---------------------------------------------------------------------

## 3. Google OAuth setup (one time)

1. Go to https://console.cloud.google.com and create/select a project.
2. **APIs & Services → OAuth consent screen**. Choose **Internal** if NEMSU uses Google Workspace
   (only NEMSU accounts can even see the login). Otherwise choose External.
3. **Credentials → Create credentials → OAuth client ID → Web application**.
4. **Authorized redirect URIs** - add exactly (**this changed from the Flask version**):
   - `http://localhost:8000/api/auth/callback`   (built app, see 4a)
   - `http://localhost:5173/api/auth/callback`   (Vite dev server, see 4b)
   - `https://YOUR-DOMAIN/api/auth/callback`     (when deployed)
5. Copy the **Client ID** and **Client secret** into `backend/.env`.
6. `PUBLIC_URL` in `backend/.env` must be the address you open in the browser
   (`http://localhost:8000` for 4a, `http://localhost:5173` for 4b). Use `localhost`, not `127.0.0.1`.

The login is Google's own page. The app never asks for or stores a Google password. After Google
replies the **server** checks: email verified, ends with `@nemsu.edu.ph`, and (if sent) hosted
domain is `nemsu.edu.ph`.

## 4. Run

**4a. One server (production-style)** - FastAPI also serves the built React app:

```bash
cd frontend && npm run build          # makes frontend/dist
cd ../backend
uvicorn app.main:app --port 8000      # open http://localhost:8000
```

Production: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2` behind HTTPS (nginx,
Caddy...) with `COOKIE_SECURE=true` and `PUBLIC_URL=https://your-domain`.

**4b. Development with hot reload** - two terminals:

```bash
cd backend  && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev            # open http://localhost:5173  (set PUBLIC_URL=http://localhost:5173)
```

API docs (development): http://localhost:8000/api/docs

## 5. Admin accounts

Only emails in `ADMIN_EMAILS` become admins (comma separated). Restart after changing it. Removing
someone removes their admin access immediately. Admins never see the Student/Instructor choice.

Admins can also sign in with **email + password** at the secret address
`/admin/login/<ADMIN_LOGIN_SECRET>` (the address is printed when the server starts). Set the
password either with `ADMIN_PASSWORD` in `.env`, or run `python -m scripts.create_admin` (saved as a
salted Argon2 hash). The dashboard (`/admin`) shows a 404 to anyone who is not a signed-in admin.

## 6. Database schema (PostgreSQL)

```
users(id, google_id UNIQUE, name, email UNIQUE, role[student|instructor|admin|NULL],
      created_at, last_login, is_active)
admin_credentials(email PK, password_hash, updated_at)
concerns(id, user_id→users, reporter_name, reporter_email, location, room, concern_type,
         description, concern_date DATE, image_filename, status, created_at, updated_at)
reports(id, user_id→users, reporter_name, reporter_email, location, area, room, report_type,
        description, report_date DATE, image_filename, status, created_at, updated_at)
feedback(id, user_id→users, name, email, area, feedback_type, message, feedback_date DATE,
         status, created_at, updated_at)
reservations(id, user_id→users, requester_name, requester_email, facility, purpose,
             reservation_date DATE, start_time TIME, end_time TIME, additional_info, status,
             created_at, updated_at)
faculty_reports(id, instructor, reason, start_date DATE, expected_return DATE, submitted_at,
                status[Absent|Available], instructor_email)          -- was a CSV
rooms(id, room_id UNIQUE, name, building, room_type, capacity, equipment, status)   -- was a CSV
campus_info(id, topic UNIQUE(case-insensitive), keywords, answer)                    -- was a CSV
```

Statuses - concerns/reports: Pending, Under Review, In Progress, Resolved, Rejected ·
feedback: Pending, Reviewed · reservations: Pending, Approved, Rejected, Cancelled.
`campus_info.keywords` are split by `;` and `a+b` means both words must appear.

Dates are real `DATE`/`TIME` columns now, so overlap checks and the dashboard trend are done by
PostgreSQL. Tables are created on start; for later schema changes add Alembic migrations.

## 7. Move your OLD data (SQLite + CSV → PostgreSQL)

Put your old project somewhere (e.g. `../old/`), then from `backend/`:

```bash
python -m scripts.import_legacy \
    --sqlite      ../old/database/campus.db \
    --faculty-csv ../old/data/faculty/faculty_availability.csv \
    --rooms-csv   ../old/data/rooms/rooms.csv \
    --campus-csv  ../old/data/campus/campus_info.csv
```

Keeps ids, so existing PDFs (`reports/…/concern_0001.pdf`) and uploaded photos still match - copy the
old `reports/` and `uploads/` folders into `backend/`. Safe to run twice (existing rows are skipped).
The old faculty CSV repairs (glued header, missing/duplicate ids) are applied automatically.
Old admin password hashes are **not** imported (different hashing library) - set `ADMIN_PASSWORD`
or run `python -m scripts.create_admin`.

## 8. Tests

**Backend** (pytest, real PostgreSQL, fake Google + fake AI - no internet or API key needed):

```bash
cd backend
TEST_DATABASE_URL=postgresql://campus:campus@localhost:5432/campusense_test pytest -q
```
(Windows PowerShell: `$env:TEST_DATABASE_URL="..."; pytest -q`.) The tests **empty the tables of that
database** - never point it at your real one. They cover every area of the old `run_checks.py`:
account rules, roles, CSRF, admin password + lock-out, privacy, uploads, PDFs, faculty answers
coming from the database (not the AI), reservations + overlap, status workflow, dashboard counts,
the AI seeing only the role.

**Frontend** (renders the real React app and clicks through it against a running backend):

```bash
# terminal 1 - backend on the TEST database, with a known admin
cd backend
export DATABASE_URL=postgresql://campus:campus@localhost:5432/campusense_test
export SECRET_KEY=test-key ADMIN_EMAILS=admin@nemsu.edu.ph ADMIN_LOGIN_SECRET=mysecrets-dev
python -m scripts.make_test_users /tmp/cookies.json
uvicorn app.main:app --port 8000
# terminal 2
cd frontend && COOKIES_FILE=/tmp/cookies.json npm test
```

Manual checks: sign in with a `@nemsu.edu.ph` account (allowed) and a Gmail account ("Please use
your official NEMSU Google account."); as a student try "The projector in Room 204 is broken.",
"Can I reserve a laboratory?", "Is Sir JP available today?", "Where is the library?",
"What is Python?"; as an instructor "I cannot work today."; as an admin change a concern's status
and ask the student chat "What is the status of my concern?".

## 9. How the browser and the server talk

- Login: the **Continue with Google** button is a normal link to `/api/auth/google`. After Google, the
  server sets a signed, HttpOnly session cookie and redirects to the React page for the user's role.
- The React app calls `GET /api/auth/me` on load: it returns the user, the menu for that role and a
  CSRF token. Every POST/DELETE sends that token in the `X-CSRF-Token` header.
- Errors are always JSON: `{"error": "message"}` with the right status (401 sign in, 403 not allowed,
  404 hidden/unknown, 400 validation, 413 file too large, 429 too many).
- Private files (PDFs, photos) are only served by `/api/pdf/...` and `/api/uploads/...` after the
  server checks the owner or admin role.

| Area | Endpoints |
|---|---|
| Auth | `GET /api/auth/google`, `GET /api/auth/callback`, `GET /api/auth/me`, `POST /api/auth/role`, `POST /api/auth/logout`, `GET/POST /api/admin/login/{secret}` |
| Chat | `POST /api/ask` |
| Forms | `POST /api/concerns`, `/api/reports`, `/api/feedback`, `/api/reservations`, `/api/faculty/submit`, `/api/faculty/available`, `GET /api/faculty/check` |
| My pages | `GET /api/home`, `/api/me/records/{kind}`, `/api/me/faculty` |
| Files | `GET /api/pdf/{kind}/{id}`, `GET /api/uploads/{filename}` |
| Admin | `/api/admin/dashboard`, `/records/{kind}` (+ `POST …/{id}/status`), `/faculty`, `/users`, `/rooms`, `/campus` |

## 10. Rules to remember (unchanged)

- Roles are checked on the server from the database. The browser cannot choose a role after the first
  selection, and can never become admin.
- Name and email on every form come from the signed-in account.
- Students see only their own submissions. Admin endpoints return 404 to non-admins.
- AI only receives the user's role - never names, emails or Google IDs.
- Faculty availability, report statuses, counts and admin lists come from the database, never from the
  AI. The AI cannot approve, resolve or submit anything.
- Anyone with a NEMSU account can pick "Instructor" on first login. To prevent that, an admin can change
  roles in **Admin → Users**.

## 11. What changed compared with the Flask version

- **Google redirect URI** is now `<PUBLIC_URL>/api/auth/callback` (was `/auth/callback`). Update it in Google Cloud Console.
- **Secrets file** moved from `secrets/.env` to `backend/.env`; new settings: `DATABASE_URL`, `PUBLIC_URL`.
- **CSV files became tables** (faculty reports, rooms, campus info), so there is one source of truth and no file locking.
  Faculty report ids are plain numbers shown as `0001` in the UI and PDFs.
- **Admin password hashes** use Argon2 (was werkzeug). The 5-wrong-tries/15-minute lock-out is the same
  and is kept in memory per server process - with several workers it is per worker; use a shared store
  (e.g. Redis) if you need a strict global limit. The same applies to the 20-questions-per-minute AI limit.
- **Pages are React routes** (`/ai`, `/concerns`, `/admin/users`…). The server renders no HTML.
- Admin actions (change status, set role, mark available, add/delete rows) update the page in place and show the
  same success/error messages instead of reloading it.
