"""Financial report generation and export service."""

import csv
from datetime import datetime, timezone
from decimal import Decimal
import io
import re
from typing import List, Optional, Sequence, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.report import FinancialReport
from app.models.transaction import Transaction
from app.repositories.investment_repository import InvestmentRepository
from app.repositories.report_repository import FinancialReportRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.report import FinancialReportRead, ReportGenerateRequest


MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


def parse_period_dates(period: str) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Attempt to parse start and end datetime bounds from period string."""
    clean = period.lower().strip()
    year_match = re.search(r"\b(20\d\d)\b", clean)
    if not year_match:
        return None, None

    year = int(year_match.group(1))

    # Match month
    for m_name, m_num in MONTH_NAMES.items():
        if m_name in clean:
            start_dt = datetime(year, m_num, 1, 0, 0, 0, tzinfo=timezone.utc)
            if m_num == 12:
                end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            else:
                end_dt = datetime(year, m_num + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            return start_dt, end_dt

    # Match quarters
    if "q1" in clean:
        return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year, 4, 1, tzinfo=timezone.utc)
    if "q2" in clean:
        return datetime(year, 4, 1, tzinfo=timezone.utc), datetime(year, 7, 1, tzinfo=timezone.utc)
    if "q3" in clean:
        return datetime(year, 7, 1, tzinfo=timezone.utc), datetime(year, 10, 1, tzinfo=timezone.utc)
    if "q4" in clean:
        return datetime(year, 10, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    # Full year
    if "year" in clean or "fy" in clean:
        return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year + 1, 1, 1, tzinfo=timezone.utc)

    return None, None


class ReportService:
    """Service handling dynamic report generation and secure data export."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.report_repo = FinancialReportRepository(db)
        self.tx_repo = TransactionRepository(db)
        self.inv_repo = InvestmentRepository(db)

    def _to_read_schema(self, report: FinancialReport) -> FinancialReportRead:
        """Convert ORM model to schema matching frontend interface."""
        date_str = report.created_at.strftime("%Y-%m-%d") if report.created_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return FinancialReportRead(
            id=report.id,
            user_id=report.user_id,
            name=report.name,
            period=report.period,
            status=report.status,  # type: ignore[arg-type]
            type=report.report_type,  # type: ignore[arg-type]
            report_type=report.report_type,  # type: ignore[arg-type]
            file_size=report.file_size,
            fileSize=report.file_size,
            download_url=report.download_url,
            downloadUrl=report.download_url,
            date=date_str,
            created_at=report.created_at or datetime.now(timezone.utc),
            updated_at=report.updated_at or datetime.now(timezone.utc),
        )

    async def list_reports(self, user_id: str) -> List[FinancialReportRead]:
        """Retrieve all financial reports for the authenticated user."""
        reports = await self.report_repo.get_by_user(user_id)
        return [self._to_read_schema(r) for r in reports]

    async def generate_report(self, user_id: str, payload: ReportGenerateRequest) -> FinancialReportRead:
        """Generate and persist a financial report based on actual user transactions."""
        report_type = payload.type or "summary"
        period = payload.period or "Current Period"

        # Determine date filter
        start_date = payload.start_date
        end_date = payload.end_date
        if not start_date and not end_date:
            parsed_start, parsed_end = parse_period_dates(period)
            start_date, end_date = parsed_start, parsed_end

        # Query user transaction count for accurate file sizing
        tx_count = await self.tx_repo.count_by_user(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Human-readable title
        titles = {
            "summary": f"Cashflow & Income Statement ({period})",
            "spending": f"Spending Category Breakdown ({period})",
            "tax": f"Tax Year Preliminary Projection ({period})",
            "portfolio": f"Investment Portfolio Performance Review ({period})",
        }
        report_name = titles.get(report_type, f"{report_type.capitalize()} Financial Report ({period})")

        # Estimate file size
        estimated_kb = max(1.2, round((tx_count * 0.35) + 1.2, 1))
        file_size_str = f"{estimated_kb} KB"

        # Create report record
        new_report = FinancialReport(
            user_id=user_id,
            name=report_name,
            period=period,
            report_type=report_type,
            status="Ready",
            file_size=file_size_str,
        )
        self.db.add(new_report)
        await self.db.commit()
        await self.db.refresh(new_report)

        # Set permanent download endpoint URL
        new_report.download_url = f"/api/v1/reports/{new_report.id}/download"
        await self.db.commit()
        await self.db.refresh(new_report)

        return self._to_read_schema(new_report)

    async def get_report_by_id(self, user_id: str, report_id: str) -> FinancialReport:
        """Fetch report ensuring strict user ownership."""
        report = await self.report_repo.get_by_id(report_id)
        if not report or report.user_id != user_id:
            raise NotFoundException("Financial report not found.")
        return report

    async def export_csv(self, user_id: str, report_id: str) -> Tuple[str, str]:
        """Generate CSV export from verified database records."""
        report = await self.get_report_by_id(user_id=user_id, report_id=report_id)

        # Parse period dates
        start_date, end_date = parse_period_dates(report.period)

        # Query real transactions for user
        txs: Sequence[Transaction] = await self.tx_repo.get_by_user_paginated(
            user_id=user_id,
            skip=0,
            limit=500,
            start_date=start_date,
            end_date=end_date,
            sort_by="date",
            sort_order="asc",
        )

        totals = await self.tx_repo.get_cashflow_totals_by_user(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        categories = await self.tx_repo.get_category_spending_by_user(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )

        income = totals["credit"]
        expenses = totals["debit"]
        savings = income - expenses
        savings_rate = 0.0
        if income > Decimal("0"):
            savings_rate = round(float((savings / income) * Decimal("100")), 1)

        output = io.StringIO()
        writer = csv.writer(output)

        # Section 1: Header
        writer.writerow(["AI Finance Advisor - Exported Financial Report"])
        writer.writerow(["Report Name", report.name])
        writer.writerow(["Report Type", report.report_type])
        writer.writerow(["Period", report.period])
        writer.writerow(["Generated At", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")])
        writer.writerow([])

        # Section 2: Report-Specific Content
        if report.report_type == "portfolio":
            portfolios = await self.inv_repo.get_portfolios_by_user(user_id=user_id)
            writer.writerow(["--- Investment Portfolio Performance & Holdings ---"])
            if portfolios:
                for port in portfolios:
                    positions = port.positions or []
                    p_val = sum((pos.total_value for pos in positions), Decimal("0.0000"))
                    p_inv = sum((pos.total_invested for pos in positions), Decimal("0.0000"))
                    p_pnl = p_val - p_inv
                    p_pct = float((p_pnl / p_inv) * Decimal("100")) if p_inv > Decimal("0") else 0.0

                    writer.writerow(["Portfolio Name", port.name])
                    writer.writerow(["Account Type", port.account_type])
                    writer.writerow(["Total Portfolio Value (INR)", f"{p_val:.2f}"])
                    writer.writerow(["Total Invested Capital (INR)", f"{p_inv:.2f}"])
                    writer.writerow(["Total Unrealized P&L (INR)", f"{p_pnl:.2f} ({p_pct:+.2f}%)"])
                    writer.writerow([])
                    writer.writerow(["Holdings:"])
                    writer.writerow(["Ticker", "Asset Name", "Shares", "Avg Buy Price", "Current Price", "Current Value", "Unrealized P&L", "Sector"])
                    for pos in positions:
                        writer.writerow([
                            pos.ticker,
                            pos.name,
                            f"{pos.shares:.4f}",
                            f"{pos.avg_price:.2f}",
                            f"{pos.current_price:.2f}",
                            f"{pos.total_value:.2f}",
                            f"{pos.pnl:+.2f} ({pos.pnl_pct:+.2f}%)",
                            pos.sector,
                        ])
                    writer.writerow([])
            else:
                writer.writerow(["No investment portfolios or active holdings recorded."])
                writer.writerow([])

        elif report.report_type == "tax":
            writer.writerow(["--- Preliminary Tax Year Cashflow Projection (Estimate Only) ---"])
            writer.writerow(["Notice", "All tax figures are informational ledger classifications, not formal tax returns."])
            writer.writerow(["Gross Recorded Receipts / Income (INR)", f"{income:.2f}"])
            writer.writerow(["Recorded Operating / Ledger Deductions (INR)", f"{expenses:.2f}"])
            writer.writerow(["Estimated Net Pre-Tax Balance (INR)", f"{savings:.2f}"])
            writer.writerow(["Status", "Preliminary Estimate - Subject to Certified Audit"])
            writer.writerow([])

        else:
            # summary or spending report
            writer.writerow(["--- Executive Summary ---"])
            writer.writerow(["Metric", "Amount (INR)"])
            writer.writerow(["Total Income (Credits)", f"{income:.2f}"])
            writer.writerow(["Total Expenses (Debits)", f"{expenses:.2f}"])
            writer.writerow(["Net Cashflow / Savings", f"{savings:.2f}"])
            writer.writerow(["Savings Rate", f"{savings_rate}%"])
            writer.writerow(["Total Transactions", str(len(txs))])
            writer.writerow([])

        # Section 3: Category Breakdown
        writer.writerow(["--- Category Breakdown ---"])
        writer.writerow(["Category", "Total Spent (INR)", "Share of Expenses"])
        if categories:
            for cat, amt in categories:
                share = (float(amt / expenses) * 100) if expenses > Decimal("0") else 0.0
                writer.writerow([cat, f"{amt:.2f}", f"{share:.1f}%"])
        else:
            writer.writerow(["No category expense data recorded for this period."])
        writer.writerow([])

        # Section 4: Detailed Transaction Ledger
        writer.writerow(["--- Transaction Ledger ---"])
        writer.writerow(["Date", "Title", "Category", "Amount (INR)", "Type", "Status", "Account"])
        if txs:
            for t in txs:
                t_date = t.date.strftime("%Y-%m-%d") if t.date else ""
                writer.writerow([
                    t_date,
                    t.title,
                    t.category,
                    f"{t.amount:.2f}",
                    t.type,
                    t.status,
                    t.account_name or "",
                ])
        else:
            writer.writerow(["No transactions found for this period."])
        writer.writerow([])

        # Section 5: Legal & Financial Disclaimer
        writer.writerow(["--- Disclaimer ---"])
        writer.writerow(["This document is generated for educational, informational, and personal planning purposes only."])
        writer.writerow(["It does not constitute certified legal, CPA, tax advisory, or registered investment advice."])

        filename = f"{report.name.lower().replace(' ', '_').replace('(', '').replace(')', '')}.csv"
        return filename, output.getvalue()
