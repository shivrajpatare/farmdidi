from typing import Optional

from pydantic import BaseModel, Field


class ProductionUpdate(BaseModel):
    production_status: str
    product: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None


class IssueUpdate(BaseModel):
    has_issue: bool
    issue_type: Optional[str] = None
    issue: Optional[str] = None
    details: Optional[str] = None


class CheckInRecord(BaseModel):
    didi_id: str
    didi_name: str
    date: str

    production_status: str
    product: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None

    has_issue: bool = False
    issue_type: Optional[str] = None
    issue: Optional[str] = None
    issue_details: Optional[str] = None

    status: str = "confirmed"


class IssueRecord(BaseModel):
    issue_id: str
    date: str
    didi_id: str
    didi_name: str
    issue_type: str
    issue: str
    issue_details: Optional[str] = None
    status: str = "open"
    resolved_at: Optional[str] = None
    resolution_notes: Optional[str] = None
