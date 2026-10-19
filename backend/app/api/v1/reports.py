"""Financial Reports API router with authenticated generation and CSV download."""

from typing import List
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.report import FinancialReportRead, ReportGenerateRequest
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("", response_model=ApiResponse[List[FinancialReportRead]], summary="List user financial reports")
async def list_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[List[FinancialReportRead]]:
    """Retrieve all financial reports generated for the authenticated user."""
    service = ReportService(db)
    reports = await service.list_reports(user_id=current_user.id)
    return ApiResponse.ok(data=reports, message="Reports retrieved successfully.")


@router.post(
    "/generate",
    response_model=ApiResponse[FinancialReportRead],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new financial report",
)
async def generate_report(
    payload: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FinancialReportRead]:
    """Generate a financial report from real user transaction records."""
    service = ReportService(db)
    report = await service.generate_report(user_id=current_user.id, payload=payload)
    return ApiResponse.ok(data=report, message="Report generated successfully.")


@router.get("/{report_id}", response_model=ApiResponse[FinancialReportRead], summary="Get report details")
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[FinancialReportRead]:
    """Get metadata for a specific report ensuring user ownership."""
    service = ReportService(db)
    report_model = await service.get_report_by_id(user_id=current_user.id, report_id=report_id)
    return ApiResponse.ok(data=service._to_read_schema(report_model), message="Report details retrieved.")


@router.get("/{report_id}/download", summary="Download report as CSV")
async def download_report_csv(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download financial report as a formatted CSV file."""
    service = ReportService(db)
    filename, csv_data = await service.export_csv(user_id=current_user.id, report_id=report_id)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )
