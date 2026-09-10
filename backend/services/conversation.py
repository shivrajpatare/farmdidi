from enum import Enum
from typing import Optional

from pydantic import BaseModel

from backend.models import IssueUpdate, ProductionUpdate


class ConversationState(str, Enum):
    START = "START"
    ASK_PRODUCTION = "ASK_PRODUCTION"
    GET_PRODUCTION = "GET_PRODUCTION"
    ASK_ISSUE = "ASK_ISSUE"
    GET_ISSUE = "GET_ISSUE"
    CONFIRM = "CONFIRM"
    AWAITING_CORRECTION = "AWAITING_CORRECTION"
    SAVE = "SAVE"
    COMPLETE = "COMPLETE"


class ConversationSession(BaseModel):
    session_id: str
    didi_id: str
    didi_name: str
    state: ConversationState = ConversationState.START
    production: Optional[ProductionUpdate] = None
    issue: Optional[IssueUpdate] = None
    confirmed: bool = False
    persisted: bool = False


class ConversationEngine:
    def start(self, session: ConversationSession) -> str:
        self._require_state(session, ConversationState.START)
        session.state = ConversationState.ASK_PRODUCTION
        return f"Good morning {session.didi_name} ji. Aaj aap kya bana rahi hain?"

    def receive_production(
        self,
        session: ConversationSession,
        production: ProductionUpdate,
    ) -> str:
        self._require_state(session, ConversationState.ASK_PRODUCTION)
        session.state = ConversationState.GET_PRODUCTION
        session.production = production
        session.state = ConversationState.ASK_ISSUE
        return "Aaj koi dikkat ya kisi cheez ki zarurat hai?"

    def receive_issue(
        self,
        session: ConversationSession,
        issue: IssueUpdate,
    ) -> str:
        self._require_state(session, ConversationState.ASK_ISSUE)
        session.state = ConversationState.GET_ISSUE
        session.issue = issue
        session.state = ConversationState.CONFIRM
        return self._confirmation_message(session)

    def confirm(self, session: ConversationSession, decision: str) -> str:
        self._require_state(session, ConversationState.CONFIRM)

        if decision == "yes":
            session.confirmed = True
            session.state = ConversationState.COMPLETE
            return "Dhanyavaad. Aapka check-in confirm ho gaya hai."
        if decision == "no":
            session.confirmed = False
            session.state = ConversationState.AWAITING_CORRECTION
            return "Thik hai. Kya change karna hai?"

        raise ValueError("Decision must be 'yes' or 'no'.")

    def apply_correction(
        self,
        session: ConversationSession,
        production: ProductionUpdate,
        issue: IssueUpdate,
    ) -> str:
        self._require_state(session, ConversationState.AWAITING_CORRECTION)
        session.production = production
        session.issue = issue
        session.state = ConversationState.CONFIRM
        session.confirmed = False
        return self._confirmation_message(session)

    @staticmethod
    def _require_state(
        session: ConversationSession,
        expected_state: ConversationState,
    ) -> None:
        if session.state is not expected_state:
            raise ValueError(
                f"Expected state {expected_state.value}, "
                f"got {session.state.value}."
            )

    @staticmethod
    def _confirmation_message(session: ConversationSession) -> str:
        production = session.production
        issue = session.issue

        quantity = (
            f"{production.quantity:g}"
            if production and production.quantity is not None
            else "unspecified"
        )
        unit = production.unit if production and production.unit else "units"
        product = production.product if production and production.product else "the planned product"

        if issue and issue.has_issue:
            issue_summary = issue.issue or "an issue"
        else:
            issue_summary = "no issue"

        return (
            f"Main confirm kar lu: {quantity} {unit} {product} "
            f"aur {issue_summary}. Ye sahi hai?"
        )
