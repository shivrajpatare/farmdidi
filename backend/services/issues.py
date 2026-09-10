from datetime import date, datetime, timezone
from typing import Optional

from backend.models import IssueRecord
from backend.services.conversation import ConversationSession, ConversationState
from backend.services.validation import validate_issue

# In-memory issue store for MVP
ISSUES: dict[str, IssueRecord] = {}


def _generate_issue_id(
    didi_id: str,
    issue_date: str,
    session_id: Optional[str] = None,
) -> str:
    """Generate a predictable unique issue identifier in the format ISS-YYYYMMDD-DIDI_ID."""
    date_compact = issue_date.replace("-", "")
    base_id = f"ISS-{date_compact}-{didi_id}"
    if base_id not in ISSUES:
        return base_id

    # If an issue already exists for this Didi on the same date, make it unique
    if session_id:
        suffix = session_id[-4:].upper()
        unique_id = f"{base_id}-{suffix}"
        if unique_id not in ISSUES:
            return unique_id

    counter = 2
    while f"{base_id}-{counter}" in ISSUES:
        counter += 1
    return f"{base_id}-{counter}"


def create_issue_record(
    session: ConversationSession,
    issue_date: Optional[str] = None,
) -> IssueRecord | None:
    """Create an IssueRecord with initial status 'open' from a confirmed check-in.
    
    Returns None if:
    - session is not COMPLETE or not confirmed
    - session has no issue or has_issue is False
    - issue fails validation or is incomplete
    """
    # 1. Enforce confirmation & completion gate
    if session.state is not ConversationState.COMPLETE or session.confirmed is not True:
        return None

    # 2. Enforce issue existence gate
    if not session.issue or not session.issue.has_issue:
        return None

    # 3. Enforce issue validation gate
    validation = validate_issue(session.issue)
    if validation.status != "valid":
        return None

    # 4. Enforce required fields
    if not session.issue.issue_type or not session.issue.issue:
        return None

    current_date = issue_date or date.today().isoformat()
    issue_id = _generate_issue_id(session.didi_id, current_date, session.session_id)

    record = IssueRecord(
        issue_id=issue_id,
        date=current_date,
        didi_id=session.didi_id,
        didi_name=session.didi_name,
        issue_type=session.issue.issue_type,
        issue=session.issue.issue,
        issue_details=session.issue.details,
        status="open",
        resolved_at=None,
        resolution_notes=None,
    )

    ISSUES[issue_id] = record
    return record


def get_issue(issue_id: str) -> IssueRecord | None:
    """Retrieve an issue record by its ID."""
    return ISSUES.get(issue_id)


def get_all_issues() -> list[IssueRecord]:
    """Return all tracked issue records."""
    return list(ISSUES.values())


def clear_issues() -> None:
    """Clear all issues (for testing purposes)."""
    ISSUES.clear()


def resolve_issue(
    issue_id: str,
    resolution_notes: Optional[str] = None,
    resolved_at: Optional[str] = None,
) -> IssueRecord:
    """Mark an open issue as resolved with human-provided resolution notes."""
    issue = get_issue(issue_id)
    if not issue:
        raise KeyError(f"Issue '{issue_id}' not found.")
    if issue.status != "open":
        raise ValueError(f"Issue '{issue_id}' is already {issue.status} and cannot be resolved again.")

    issue.status = "resolved"
    issue.resolved_at = resolved_at or datetime.now(timezone.utc).isoformat()
    issue.resolution_notes = resolution_notes.strip() if resolution_notes and resolution_notes.strip() else None
    return issue
