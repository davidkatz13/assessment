import uuid
from datetime import datetime

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import Controllers
from app.models.schemas import BatchSubmitResponse, PaginatedBatches
from core.enums import BatchStatus

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("", response_model=BatchSubmitResponse)
async def submit_batch(
    controllers: Controllers, file: UploadFile = File(...)
) -> JSONResponse:
    """Ingest one batch file, atomically committing or rejecting all of its claims."""
    batch_controller = controllers.build_batch_controller()
    response, status_code = await batch_controller.submit_batch(file)
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json")
    )


@router.get("", response_model=PaginatedBatches)
def list_batches(
    controllers: Controllers,
    batch_id: uuid.UUID | None = None,
    status_filter: BatchStatus | None = Query(None, alias="status"),
    submitted_after: datetime | None = None,
    submitted_before: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PaginatedBatches:
    """List/search previously submitted batches, newest first."""
    batch_controller = controllers.build_batch_controller()
    return batch_controller.list_batches(
        batch_id=batch_id,
        status=status_filter,
        submitted_after=submitted_after,
        submitted_before=submitted_before,
        limit=limit,
        offset=offset,
    )
