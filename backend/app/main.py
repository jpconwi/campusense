"""
main.py - starts CampusSense AI (FastAPI).

Development:  uvicorn app.main:app --reload          (from the backend/ folder)
Production:   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

If the React app was built (frontend/dist exists) FastAPI serves it too, so one
process runs the whole site. Otherwise run the Vite dev server (see README).
"""

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.database import init_db
from app.routers import admin, admin_login, api, auth
from app.services.common import ValidationError


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_folders()
    if config.admin_password() and len(config.admin_password()) < config.ADMIN_MIN_PASSWORD:
        raise RuntimeError(f"ADMIN_PASSWORD in backend/.env must be at least "
                           f"{config.ADMIN_MIN_PASSWORD} characters.")
    init_db()
    print(f"Admin login: {config.PUBLIC_URL}{config.ADMIN_LOGIN_URL}  (keep this private)")
    yield


def create_app():
    app = FastAPI(title="CampusSense AI", lifespan=lifespan,
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")

    secret = config.SECRET_KEY
    if not secret:
        secret = secrets.token_hex(32)
        print("WARNING: SECRET_KEY is missing in backend/.env. Using a temporary key; "
              "everyone will be signed out whenever the app restarts.")

    max_body = (config.MAX_UPLOAD_MB + 1) * 1024 * 1024

    # ------------------------------------------------ extra headers + size limit
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_body:
            return JSONResponse(
                {"error": f"The file is too large. The maximum is {config.MAX_UPLOAD_MB} MB."},
                status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Session cookie (signed, HttpOnly). Added last so it wraps everything above.
    app.add_middleware(
        SessionMiddleware, secret_key=secret, session_cookie="campusense_session",
        max_age=config.SESSION_HOURS * 3600, same_site="lax", https_only=config.COOKIE_SECURE)

    app.include_router(auth.router)
    app.include_router(admin_login.router)
    app.include_router(admin.router)
    app.include_router(api.router)

    # ---------------------------------------------------- error handlers
    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc: ValidationError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return JSONResponse({"error": "Please check the form and try again."}, status_code=400)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        print("SERVER ERROR:", repr(exc))
        return JSONResponse({"error": "Something went wrong. Please try again."}, status_code=500)

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI):
    """Serve the built React app (frontend/dist) with index.html as the fallback."""
    dist = config.FRONTEND_DIST
    if not (dist / "index.html").exists():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse({"error": "That page was not found."}, status_code=404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
