from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import batches, claims
from core.exceptions import BatchTooLargeError
from core.logging import configure_logging

configure_logging()

app = FastAPI(title="MarvelX Batch Document Processor")

app.include_router(batches.router, prefix="/api/v1")
app.include_router(claims.router, prefix="/api/v1")


@app.exception_handler(BatchTooLargeError)
async def handle_batch_too_large(
    request: Request, exc: BatchTooLargeError
) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": str(exc)})
