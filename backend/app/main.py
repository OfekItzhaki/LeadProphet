import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.dependencies import get_current_user, get_optional_user
from app.db import get_db
from app.exceptions import PipelineError
from app.models import User
from app.routers import auth, campaigns, events, ingestion, jobs, leads, metrics, outreach, outbound, public, quality, ui, workflow
from app.schemas import UserRead

logger = logging.getLogger(__name__)

if settings.is_production and not settings.jwt_secret_key:
    raise RuntimeError("JWT_SECRET_KEY is required in production")
if settings.is_production and settings.database_url.startswith("sqlite") and not settings.allow_sqlite_in_production_rehearsal:
    raise RuntimeError("DATABASE_URL must use PostgreSQL in production")

app = FastAPI(
    title="LeadProphet",
    version=settings.app_version,
    docs_url="/docs" if settings.expose_docs else None,
    redoc_url="/redoc" if settings.expose_docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.effective_jwt_secret_key,
    https_only=settings.secure_cookies,
    same_site=settings.cookie_samesite,
)
app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(leads.router)
app.include_router(ingestion.router)
app.include_router(jobs.router)
app.include_router(metrics.router)
app.include_router(events.router)
app.include_router(quality.router)
app.include_router(outreach.router)
app.include_router(workflow.router)
app.include_router(outbound.router)
app.include_router(public.router)
app.include_router(ui.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.state.templates = Jinja2Templates(directory="app/templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    import uuid
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed", "code": "validation_error", "errors": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if "text/html" in request.headers.get("accept", "") and request.app.state.templates:
        with next(get_db()) as db:
            current_user = get_optional_user(request, db)
        title = "Page not found" if exc.status_code == 404 else "Something went wrong"
        return request.app.state.templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"status_code": exc.status_code, "title": title, "message": str(exc.detail), "current_user": current_user},
            status_code=exc.status_code,
        )
    code = "authentication_required" if exc.status_code == 401 else "request_error"
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": code}, headers=exc.headers)


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if "text/html" in request.headers.get("accept", "") and request.app.state.templates:
        db = next(get_db())
        try:
            current_user = get_optional_user(request, db)
        finally:
            db.close()
        title = "Page not found" if exc.status_code == 404 else "Something went wrong"
        return request.app.state.templates.TemplateResponse(
            request=request, name="error.html",
            context={"status_code": exc.status_code, "title": title, "message": str(exc.detail), "current_user": current_user},
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": "request_error"})


@app.exception_handler(PipelineError)
async def pipeline_exception_handler(request: Request, exc: PipelineError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": exc.detail, "code": "pipeline_error", "lead_id": exc.lead_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled request error path=%s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "code": "internal_error"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    from app.db import SessionLocal
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/me", response_model=UserRead, tags=["auth"])
def current_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user
