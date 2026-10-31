"""The web API and the front end, in one process.

Run:  .venv/bin/uvicorn api.main:app --port 8080
Modes (TUTOR_MODE): all = teacher and student routes | teacher = private instance | student = the exam link only.
A student-only instance has no teacher routes at all (they answer 404), so it is safe to expose on a network.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from tutor import config

from .routes import public, teacher
from .security import RateLimiter, origin_is_allowed
from .settings import Settings, load_settings

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    docs = os.environ.get("API_DOCS") == "1" and settings.mode != "student"
    app = FastAPI(title="Adaptive Tutor", version="1.0.0", docs_url="/api/docs" if docs else None,
                  redoc_url=None, openapi_url="/api/openapi.json" if docs else None)
    app.state.settings, app.state.limiter = settings, RateLimiter()
    app.add_middleware(GZipMiddleware, minimum_size=800)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and request.method in UNSAFE:
            if not origin_is_allowed(request):
                return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
            size = int(request.headers.get("content-length") or 0)
            if path.endswith("/exams/upload") and size > (config.MAX_UPLOAD_MB + 2) * 1024 * 1024:
                return JSONResponse({"detail": f"The file is larger than {config.MAX_UPLOAD_MB} MB."}, status_code=413)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                                 "Referrer-Policy": "same-origin", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"})
        if not docs or not path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = CSP
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"          # student answers and class results are private
        elif path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"   # file names carry a content hash
        return response

    @app.exception_handler(RequestValidationError)
    async def readable_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path", "form"))
        return JSONResponse({"detail": f"{field}: {first.get('msg', 'invalid value')}" if field else "Invalid request."}, status_code=422)

    app.include_router(public.router, prefix="/api")             # first, so /exams/{code}/join is the student route
    if settings.mode in ("all", "teacher"):
        app.include_router(teacher.auth, prefix="/api")
        app.include_router(teacher.router, prefix="/api")
    _mount_web(app, settings.web_dist)
    return app


def _mount_web(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        @app.get("/", include_in_schema=False)
        def not_built() -> dict:
            return {"message": "The API is running. Build the front end first: cd web && npm install && npm run build"}
        return
    from fastapi.staticfiles import StaticFiles

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:       # favicon, robots.txt, fonts
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})     # every other path is a page of the app


app = create_app()
