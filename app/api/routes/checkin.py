from datetime import datetime, timezone

from fastapi import APIRouter

from ..schemas.checkin import CheckinRequest, CheckinResponse


router = APIRouter(tags=["checkin"])


@router.post("/", response_model=CheckinResponse, summary="Create a check-in event")
def create_checkin(payload: CheckinRequest) -> CheckinResponse:
    event_time = payload.timestamp or datetime.now(timezone.utc)
    _ = event_time.isoformat()
    return CheckinResponse(status="ok", message="Check-in recorded")



