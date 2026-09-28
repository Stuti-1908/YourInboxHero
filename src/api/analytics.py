from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date
from pydantic import BaseModel
from typing import Dict, List

from src.db import get_db
from src.auth import get_current_user
from src.models.user import User
from src.models.invoice import Invoice
from src.models.debtor import Debtor

router = APIRouter()

class AgingReport(BaseModel):
    current: float
    days_30: float
    days_60: float
    days_90_plus: float

class MonthlyRecovered(BaseModel):
    month: str
    amount: float

class AnalyticsResponse(BaseModel):
    total_outstanding: float
    total_recovered: float
    recovery_rate: float
    aging: AgingReport
    status_breakdown: Dict[str, int]
    monthly_recovered: List[MonthlyRecovered]

@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    invoices = (
        db.query(Invoice)
        .join(Debtor, Invoice.debtor_id == Debtor.id)
        .filter(Debtor.user_id == current_user.id)
        .all()
    )

    total_outstanding = 0.0
    total_recovered = 0.0
    status_breakdown = {}
    
    aging = {
        "current": 0.0,
        "days_30": 0.0,
        "days_60": 0.0,
        "days_90_plus": 0.0
    }

    monthly_dict = {}
    today = date.today()

    for inv in invoices:
        amt = float(inv.amount)
        status_name = inv.status.name if hasattr(inv.status, "name") else str(inv.status)
        if hasattr(inv.status, "value"):
            status_name = inv.status.value

        status_breakdown[status_name] = status_breakdown.get(status_name, 0) + 1

        if status_name == "paid":
            total_recovered += amt
            if inv.due_date:
                month_str = inv.due_date.strftime("%Y-%m")
                monthly_dict[month_str] = monthly_dict.get(month_str, 0.0) + amt
        else:
            total_outstanding += amt
            if inv.due_date:
                days_diff = (today - inv.due_date).days
                if days_diff < 30:
                    aging["current"] += amt
                elif 30 <= days_diff < 60:
                    aging["days_30"] += amt
                elif 60 <= days_diff < 90:
                    aging["days_60"] += amt
                else:
                    aging["days_90_plus"] += amt

    recovery_rate = 0.0
    if (total_outstanding + total_recovered) > 0:
        recovery_rate = (total_recovered / (total_outstanding + total_recovered)) * 100

    monthly_recovered_list = [
        MonthlyRecovered(month=m, amount=a) for m, a in sorted(monthly_dict.items())
    ]

    return AnalyticsResponse(
        total_outstanding=total_outstanding,
        total_recovered=total_recovered,
        recovery_rate=round(recovery_rate, 2),
        aging=AgingReport(**aging),
        status_breakdown=status_breakdown,
        monthly_recovered=monthly_recovered_list
    )
