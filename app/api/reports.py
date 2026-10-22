from fastapi import APIRouter

from app.database.connection import SessionDep
from app.schemas.report import SummaryRead
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary", response_model=SummaryRead)
def get_summary(session: SessionDep) -> SummaryRead:
    return report_service.get_summary(session)
