import json
import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from backend.models import IssueUpdate, ProductionUpdate


ValidationStatus = Literal["valid", "incomplete", "invalid"]


class ValidationResult(BaseModel):
	valid: bool
	status: ValidationStatus
	errors: list[str] = Field(default_factory=list)
	warnings: list[str] = Field(default_factory=list)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_didis() -> dict[str, dict]:
	with (DATA_DIR / "didis.json").open(encoding="utf-8") as file:
		return {didi["didi_id"]: didi for didi in json.load(file)}


def _load_products() -> dict[str, dict]:
	with (DATA_DIR / "products.json").open(encoding="utf-8") as file:
		return {product["name"]: product for product in json.load(file)}


def _result(
	status: ValidationStatus,
	errors: list[str],
	warnings: list[str] | None = None,
) -> ValidationResult:
	return ValidationResult(
		valid=status == "valid",
		status=status,
		errors=errors,
		warnings=warnings or [],
	)


def validate_production(
	didi_id: str,
	production: ProductionUpdate,
) -> ValidationResult:
	"""Validate a parsed production update without calling any external service."""
	errors: list[str] = []
	incomplete: list[str] = []

	didi = _load_didis().get(didi_id)
	if didi is None:
		errors.append("Didi ID is not recognized.")
	elif not didi.get("active", False):
		errors.append("Didi is inactive.")

	if not isinstance(production, ProductionUpdate):
		return _result("invalid", ["Production data is not a valid ProductionUpdate."])

	if production.production_status == "none":
		return _result("invalid" if errors else "valid", errors)

	if production.production_status == "unclear":
		incomplete.append("Production status is unclear.")
	elif production.production_status not in {"planned", "completed"}:
		errors.append("Production status is not supported.")

	product = _load_products().get(production.product or "")
	if production.production_status in {"planned", "completed"}:
		if not production.product:
			incomplete.append("Production product is missing.")
		elif " or " in (production.product or "").lower() or " ya " in (production.product or "").lower():
			incomplete.append(f"Production product is ambiguous: {production.product}")
		elif product is None or not product.get("active", False):
			errors.append("Production product is not in the active catalog.")

		if production.quantity is None:
			incomplete.append("Production quantity is missing.")
		elif not math.isfinite(production.quantity) or production.quantity <= 0:
			errors.append("Production quantity must be finite and greater than zero.")

		if production.quantity is not None and not production.unit:
			incomplete.append("Production unit is missing.")
		elif production.unit and product and production.unit != product.get("unit"):
			errors.append("Production unit does not match the product catalog.")

	if errors:
		return _result("invalid", errors, incomplete)
	if incomplete:
		return _result("incomplete", incomplete)
	return _result("valid", [])


def validate_issue(issue: IssueUpdate) -> ValidationResult:
	"""Validate a parsed issue update without calling any external service."""
	if not isinstance(issue, IssueUpdate):
		return _result("invalid", ["Issue data is not a valid IssueUpdate."])

	if not issue.has_issue:
		if any(
			value is not None
			for value in (issue.issue_type, issue.issue, issue.details)
		):
			return _result(
				"invalid",
				["Issue fields must be empty when has_issue is false."],
			)
		return _result("valid", [])

	supported_issue_types = {
		"inventory",
		"raw_material",
		"equipment",
		"production",
		"personal",
		"other",
		"unknown",
	}

	if issue.issue_type is None:
		return _result("incomplete", ["Issue type is missing."])
	if issue.issue_type not in supported_issue_types:
		return _result("invalid", ["Issue type is not supported."])
	if issue.issue is None or not issue.issue.strip():
		return _result("incomplete", ["More information about the issue is needed."])

	return _result("valid", [])
