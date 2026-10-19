"""Financial report Pydantic schemas."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


ReportType = Literal["summary", "tax", "spending", "portfolio"]
ReportStatus = Literal["Ready", "Processing", "Failed"]


class ReportGenerateRequest(BaseModel):
    """Schema for requesting report generation."""
    type: Optional[ReportType] = None
    report_type: Optional[ReportType] = Field(default=None, alias="reportType")
    period: Optional[str] = Field(default="Current Period", max_length=50)
    start_date: Optional[datetime] = Field(default=None, alias="startDate")
    end_date: Optional[datetime] = Field(default=None, alias="endDate")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def validate_report_params(self):
        effective_type = self.type or self.report_type or "summary"
        self.type = effective_type
        self.report_type = effective_type

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")
        return self


class FinancialReportBase(BaseModel):
    """Base financial report properties."""
    name: str = Field(..., min_length=1, max_length=255)
    period: str = Field(..., min_length=1, max_length=50)
    report_type: ReportType = "summary"
    status: ReportStatus = "Ready"
    file_size: Optional[str] = Field(default=None, max_length=50)
    download_url: Optional[str] = Field(default=None, max_length=512)


class FinancialReportCreate(FinancialReportBase):
    """Schema for creating a report record."""
    pass


class FinancialReportRead(BaseModel):
    """Schema for reading report details matching frontend FinancialReport interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, serialize_by_alias=True)

    id: str
    user_id: str
    name: str
    period: str
    status: ReportStatus = "Ready"
    type: ReportType
    report_type: ReportType = Field(alias="report_type")
    file_size: Optional[str] = Field(default=None, alias="fileSize")
    fileSize: Optional[str] = None
    download_url: Optional[str] = Field(default=None, alias="downloadUrl")
    downloadUrl: Optional[str] = None
    date: str
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def populate_aliases(self):
        if not self.fileSize and self.file_size:
            self.fileSize = self.file_size
        if not self.file_size and self.fileSize:
            self.file_size = self.fileSize
        if not self.downloadUrl and self.download_url:
            self.downloadUrl = self.download_url
        if not self.download_url and self.downloadUrl:
            self.download_url = self.downloadUrl
        return self
