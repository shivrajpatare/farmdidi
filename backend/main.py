import json
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date
from typing import Optional

from backend.config import settings
from backend.models import CheckInRecord, IssueRecord, IssueUpdate, ProductionUpdate
from backend.services.ai import (
    parse_correction_message,
    parse_issue_message,
    parse_production_message,
)
from backend.services.conversation import (
    ConversationEngine,
    ConversationSession,
    ConversationState,
)
from backend.services.validation import validate_issue, validate_production
from backend.services.google_sheets import (
    is_daily_checkin_persisted,
    save_checkin,
    test_apps_script_connection,
)
from backend.services.issues import (
    create_issue_record,
    get_all_issues,
    get_issue,
    resolve_issue,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load demo data
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(DATA_DIR, "didis.json")) as f:
    DIDIS = {d["didi_id"]: d for d in json.load(f)}

# ---------------------------------------------------------------------------
# In-memory session storage (MVP only)
# ---------------------------------------------------------------------------

sessions: dict[str, ConversationSession] = {}
engine = ConversationEngine()

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FarmDidi Daily Production Check-in",
    version="0.1.0",
)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://farmdidi.vercel.app",
    "https://farmdidi-5h5qjlbyd-shivraj-patares-projects.vercel.app",
]

allowed_origins = list(DEFAULT_ALLOWED_ORIGINS)
if settings.frontend_url:
    for url in settings.frontend_url.split(","):
        cleaned = url.strip().rstrip("/")
        if cleaned and cleaned not in allowed_origins:
            allowed_origins.append(cleaned)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://farmdidi.*\.vercel\.app$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    session_id: str
    didi_id: str


class ProductionRequest(BaseModel):
    session_id: str
    message: str


class IssueRequest(BaseModel):
    session_id: str
    message: str


class ConfirmRequest(BaseModel):
    session_id: str
    decision: str


class CorrectionRequest(BaseModel):
    session_id: str
    message: str


class ResolveIssueRequest(BaseModel):
    resolution_notes: Optional[str] = None


class CheckinResponse(BaseModel):
    session_id: str
    state: str
    validation_status: str | None = None
    message: str
    sheet_saved: Optional[bool] = None


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    return {
        "name": "FarmDidi Daily Production Check-in",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
    }


@app.get("/api/sheets/test")
def test_sheets_connection():
    try:
        apps_script_response = test_apps_script_connection()
    except RuntimeError as error:
        logger.warning("Google Apps Script test failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail="Google Sheets connectivity is unavailable.",
        )

    return {
        "success": True,
        "google_sheets": True,
        "message": "Google Apps Script connection successful.",
        "apps_script": apps_script_response,
    }


@app.post("/api/sheets/test-write")
def test_sheets_write():
    record = CheckInRecord(
        date="2026-09-10",
        didi_id="D001",
        didi_name="Meena",
        production_status="planned",
        product="Mango Achar",
        quantity=20,
        unit="kg",
        has_issue=True,
        issue_type="inventory",
        issue="Bottle shortage",
        issue_details="Only 30 bottles available",
        status="confirmed",
    )

    try:
        result = save_checkin(record, state="COMPLETE", confirmed=True)
    except (RuntimeError, ValueError) as error:
        logger.warning("Google Sheets test write failed: %s", error)
        raise HTTPException(
            status_code=502,
            detail="Google Sheets test write failed.",
        )

    return {
        "success": True,
        "google_sheets": True,
        "message": "One controlled confirmed record was written.",
        "apps_script": result,
    }


# ---------------------------------------------------------------------------
# Check-in API
# ---------------------------------------------------------------------------


@app.post("/api/checkin/start", response_model=CheckinResponse)
def start_checkin(req: StartRequest):
    didi = DIDIS.get(req.didi_id)
    if not didi:
        raise HTTPException(status_code=404, detail="Didi not found")

    session = ConversationSession(
        session_id=req.session_id,
        didi_id=didi["didi_id"],
        didi_name=didi["name"],
    )

    message = engine.start(session)
    sessions[req.session_id] = session

    return CheckinResponse(
        session_id=session.session_id,
        state=session.state.value,
        validation_status="valid",
        message=message,
    )


@app.post("/api/checkin/production", response_model=CheckinResponse)
def receive_production(req: ProductionRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state is not ConversationState.ASK_PRODUCTION:
        raise HTTPException(status_code=400, detail="Session is not awaiting production details.")
    if not req.message.strip():
        return CheckinResponse(
            session_id=session.session_id,
            state=session.state.value,
            validation_status="incomplete",
            message="Please tell me what you are planning to make.",
        )

    try:
        production = parse_production_message(req.message)

        # ── Merge with existing partial candidate ──
        # If the session already holds a partial production candidate and the new
        # parse is also partial, merge them so that multi-turn inputs accumulate.
        existing = session.production
        if existing is not None and production.production_status != "none":
            merged = ProductionUpdate(
                production_status=(
                    production.production_status
                    if production.production_status not in (None, "unclear")
                    else existing.production_status
                ),
                product=production.product if production.product else existing.product,
                quantity=production.quantity if production.quantity is not None else existing.quantity,
                unit=production.unit if production.unit else existing.unit,
            )
            production = merged

        validation = validate_production(session.didi_id, production)
        if validation.status != "valid":
            # Store partial candidate even when incomplete so next message can merge
            session.production = production
            return CheckinResponse(
                session_id=session.session_id,
                state=session.state.value,
                validation_status=validation.status,
                message=_production_validation_message(validation.status, validation.errors),
            )
        message = engine.receive_production(session, production)
    except (RuntimeError, ValueError) as e:
        logger.warning("Production request failed: %s", e)
        raise HTTPException(status_code=422, detail="We could not understand that production response.")

    return CheckinResponse(
        session_id=session.session_id,
        state=session.state.value,
        validation_status="valid",
        message=message,
    )


@app.post("/api/checkin/issue", response_model=CheckinResponse)
def receive_issue(req: IssueRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state is not ConversationState.ASK_ISSUE:
        raise HTTPException(status_code=400, detail="Session is not awaiting issue details.")
    if not req.message.strip():
        return CheckinResponse(
            session_id=session.session_id,
            state=session.state.value,
            validation_status="incomplete",
            message="Please tell me whether you are facing any issue.",
        )

    try:
        issue = parse_issue_message(req.message)
        validation = validate_issue(issue)
        if validation.status != "valid":
            return CheckinResponse(
                session_id=session.session_id,
                state=session.state.value,
                validation_status=validation.status,
                message="Thik hai. Kis cheez mein problem hai?",
            )
        message = engine.receive_issue(session, issue)
    except (RuntimeError, ValueError) as e:
        logger.warning("Issue request failed: %s", e)
        raise HTTPException(status_code=422, detail="We could not understand that issue response.")

    return CheckinResponse(
        session_id=session.session_id,
        state=session.state.value,
        validation_status="valid",
        message=message,
    )


@app.post("/api/checkin/confirm", response_model=CheckinResponse)
def confirm_checkin(req: ConfirmRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if req.decision not in {"yes", "no"}:
        raise HTTPException(status_code=400, detail="Decision must be 'yes' or 'no'.")
    if session.state is not ConversationState.CONFIRM:
        if session.state is ConversationState.COMPLETE:
            raise HTTPException(
                status_code=400,
                detail="Session is already COMPLETE and cannot be confirmed again.",
            )
        raise HTTPException(
            status_code=400,
            detail=f"Expected state CONFIRM, got {session.state.value}.",
        )
    if req.decision == "yes":
        today_str = date.today().isoformat()
        if is_daily_checkin_persisted(session.didi_id, today_str):
            raise HTTPException(
                status_code=409,
                detail=f"A daily check-in for {session.didi_name} ({session.didi_id}) on {today_str} has already been confirmed and recorded.",
            )

    try:
        message = engine.confirm(session, req.decision)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    sheet_saved: Optional[bool] = None

    if req.decision == "yes":
        if session.production is None:
            raise HTTPException(
                status_code=409,
                detail="Session production details are missing.",
            )

        record = CheckInRecord(
            didi_id=session.didi_id,
            didi_name=session.didi_name,
            date=date.today().isoformat(),
            production_status=session.production.production_status,
            product=session.production.product,
            quantity=session.production.quantity,
            unit=session.production.unit,
            has_issue=session.issue.has_issue if session.issue else False,
            issue_type=session.issue.issue_type if session.issue else None,
            issue=session.issue.issue if session.issue else None,
            issue_details=session.issue.details if session.issue else None,
            status="confirmed",
        )

        try:
            save_checkin(
                record,
                state=session.state.value,
                confirmed=session.confirmed,
                session_id=session.session_id,
            )
            session.persisted = True
            sheet_saved = True
            message = f"Dhanyawad {session.didi_name} ji! Aapka aaj ka check-in confirm ho gaya hai."
        except (RuntimeError, ValueError) as err:
            logger.warning("Google Sheets save failed: %s", err)
            session.persisted = False
            sheet_saved = False
            message = "Check-in confirm ho gaya hai, lekin record save nahi ho paya. Kripya thodi der baad try karein."

        create_issue_record(session)

    return CheckinResponse(
        session_id=session.session_id,
        state=session.state.value,
        validation_status="valid",
        message=message,
        sheet_saved=sheet_saved,
    )


@app.post("/api/checkin/correct", response_model=CheckinResponse)
def correct_checkin(req: CorrectionRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.state is not ConversationState.AWAITING_CORRECTION:
        raise HTTPException(status_code=400, detail="Session is not awaiting a correction.")
    if not req.message.strip():
        return CheckinResponse(
            session_id=session.session_id,
            state=session.state.value,
            validation_status="incomplete",
            message="Thik hai. Kya change karna hai?",
        )
    if session.production is None or session.issue is None:
        raise HTTPException(status_code=409, detail="Session data is incomplete for correction.")

    try:
        candidate_production, candidate_issue = parse_correction_message(
            req.message,
            session.production,
            session.issue,
        )
        if (
            candidate_production == session.production
            and candidate_issue == session.issue
        ):
            # No-op correction: the user didn't specify a meaningful change.
            # Transition back to CONFIRM so they can either confirm or try again.
            session.state = ConversationState.CONFIRM
            session.confirmed = False
            confirmation_msg = engine._confirmation_message(session)
            return CheckinResponse(
                session_id=session.session_id,
                state=session.state.value,
                validation_status="valid",
                message=(
                    "Koi baat nahi. Agar sab sahi hai, 'Yes, correct' dabaiye. "
                    "Agar kuch badalna hai, quantity ya product bata dijiye.\n\n"
                    + confirmation_msg
                ),
            )
        production_validation = validate_production(session.didi_id, candidate_production)
        issue_validation = validate_issue(candidate_issue)
        if production_validation.status != "valid":
            return CheckinResponse(
                session_id=session.session_id,
                state=session.state.value,
                validation_status=production_validation.status,
                message="Quantity ya production details ko thoda aur clearly batayein.",
            )
        if issue_validation.status != "valid":
            return CheckinResponse(
                session_id=session.session_id,
                state=session.state.value,
                validation_status=issue_validation.status,
                message="Issue details ko thoda aur clearly batayein.",
            )
        message = engine.apply_correction(session, candidate_production, candidate_issue)
    except (RuntimeError, ValueError) as e:
        logger.warning("Correction request failed: %s", e)
        raise HTTPException(status_code=422, detail="We could not understand that correction.")

    return CheckinResponse(
        session_id=session.session_id,
        state=session.state.value,
        validation_status="valid",
        message=message,
    )


def _production_validation_message(status: str, errors: list[str]) -> str:
    if status == "incomplete" and any("quantity" in error.lower() for error in errors):
        return "Quantity kitni hai? Please quantity batayein."
    if status == "invalid" and any("product" in error.lower() for error in errors):
        return "Product catalog mein ye product nahi mila."
    return "Thoda aur production detail batayein."


# ---------------------------------------------------------------------------
# Issue Management API (Human Resolution)
# ---------------------------------------------------------------------------


@app.post("/api/issues/{issue_id}/resolve", response_model=IssueRecord)
def resolve_issue_endpoint(issue_id: str, req: ResolveIssueRequest):
    issue = get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found.")
    if issue.status != "open":
        raise HTTPException(
            status_code=400,
            detail=f"Issue '{issue_id}' is already resolved and cannot be resolved again.",
        )

    try:
        updated = resolve_issue(issue_id, req.resolution_notes)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found.")
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    return updated


@app.get("/api/issues", response_model=list[IssueRecord])
def list_issues_endpoint():
    return get_all_issues()


@app.get("/api/issues/{issue_id}", response_model=IssueRecord)
def get_issue_endpoint(issue_id: str):
    issue = get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found.")
    return issue
