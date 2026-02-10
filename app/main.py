import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import auth, billing, contracts, users
from app.api.routes.admin import accounts, auth_events, billing_events, contracts as admin_contracts, users as admin_users
from app.core.config import get_settings
from app.schemas.common import CommonResponse
from app.db.session import engine
from app.services.email import email_service

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup.complete", env=settings.app_env)
    yield
    await engine.dispose()
    await email_service.close()
    logger.info("shutdown.complete")


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=settings.cors_origins_list,
#     allow_credentials=settings.cors_allow_credentials,
#     allow_methods=settings.cors_methods_list,
#     allow_headers=settings.cors_headers_list,
# )
app.include_router(auth.router)
app.include_router(contracts.router)
app.include_router(billing.router)
app.include_router(users.router)
app.include_router(admin_users.router)
app.include_router(accounts.router)
app.include_router(admin_contracts.router)
app.include_router(auth_events.router)
app.include_router(billing_events.router)


@app.get("/health", response_model=CommonResponse[dict[str, str]], tags=["health"])
async def health() -> CommonResponse[dict[str, str]]:
    return CommonResponse(data={"status": "ok"}, status_code=200)


@app.get("/health/email", response_model=CommonResponse[dict[str, str]], tags=["health"])
@app.get("/health/smtp", response_model=CommonResponse[dict[str, str]], tags=["health"])
async def health_email() -> CommonResponse[dict[str, str]]:
    try:
        await email_service.check_connection()
    except Exception as exc:
        logger.error("health.email_provider_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Email provider check failed: {exc.__class__.__name__}: {str(exc)}",
        ) from exc
    return CommonResponse(
        data={"status": "ok", "provider": "resend"},
        message="Email provider connection successful.",
        status_code=status.HTTP_200_OK,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=CommonResponse(
            success=False,
            message=exc.detail if isinstance(exc.detail, str) else "Request failed",
            status_code=exc.status_code,
        ).model_dump(),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=CommonResponse(
            success=False,
            message="Validation error",
            data={"errors": exc.errors()},
            status_code=422,
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content=CommonResponse(
            success=False,
            message="Internal server error",
            status_code=500,
        ).model_dump(),
    )
