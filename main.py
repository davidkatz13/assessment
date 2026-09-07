from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import batches, claims
from core.config import settings
from core.exceptions import BatchTooLargeError
from core.logging import configure_logging

configure_logging()

app = FastAPI(title="MarvelX Batch Document Processor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(batches.router, prefix="/api/v1")
app.include_router(claims.router, prefix="/api/v1")


@app.exception_handler(BatchTooLargeError)
async def handle_batch_too_large(
    request: Request, exc: BatchTooLargeError
) -> JSONResponse:
    """Return a 413 in the same {"detail": [{"field", "message"}]} shape used for
    every other generic request error, instead of FastAPI's bare-string default."""
    return JSONResponse(
        status_code=413, content={"detail": [{"field": "file", "message": str(exc)}]}
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Reshape FastAPI's default (verbose, loc/msg/type/input/url per error) into the
    same {"detail": [{"field", "message"}]} envelope used everywhere else that isn't
    a batch submission result -- one consistent shape for every generic request
    error (bad query param, bad path param, malformed body) across the whole API.
    """
    errors = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:])
            or str(error["loc"][-1]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})
