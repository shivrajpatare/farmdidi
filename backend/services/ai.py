import json
import logging
import re
from typing import Optional

from backend.models import IssueUpdate, ProductionUpdate
from backend.services.groq_client import _get_client, GROQ_MODEL

logger = logging.getLogger(__name__)

PRODUCTION_EXTRACTION_SYSTEM_PROMPT = """You are an AI assistant for FarmDidi, an organization supporting rural women entrepreneurs (Didis) in India.
Your task is to extract structured production information from a Didi's Hindi/Hinglish message.

Available Products Catalog:
- "Mango Achar" (Hindi: aam ka achar, aam achar, mango pickle)
- "Lemon Achar" (Hindi: nimbu ka achar, nimbu achar, lemon pickle)
- "Chilli Achar" (Hindi: mirchi ka achar, mirch achar, hari mirch achar, chilli pickle)
- "Mixed Achar" (Hindi: mix achar, mixed achar, sabzi achar)
- "Garlic Achar" (Hindi: lahsun ka achar, lasun achar, garlic pickle)

Output MUST be a single valid JSON object with the following keys:
- "production_status": string, one of ["planned", "completed", "none", "unclear"]
    - "planned": if Didi states what she is making/plans to make (e.g. "banaungi", "banayenge", "bana rahe hain", "banana hai", or directly stating the product and quantity such as "Mirchi ka achar das kilo")
    - "completed": if explicitly already completed/finished ("bana liya", "ban gaya", "taiyaar ho gaya")
    - "none": if no production today ("kuch nahi banaungi", "chhutti hai", "production nahi hai", "nahi banayenge")
    - "unclear": if the intent is completely unrelated, nonsensical, or cannot be understood
- "product": string or null. Use the standard catalog name when recognized (e.g. "Mango Achar", "Lemon Achar", "Chilli Achar", "Mixed Achar", "Garlic Achar"). Set to null if production_status is "none" or no product is mentioned. If a product is clearly mentioned but is not in the catalog, preserve its stated product name so Python validation can reject it as an invalid product; do not substitute a catalog product.
- "quantity": number (float or int) or null. Convert Hindi number words to numeric values (e.g. "bees" -> 20, "pandrah" -> 15, "das" -> 10, "paanch" -> 5, "pachees" -> 25). If quantity is ambiguous, uncertain, or given as an unresolved range (e.g. "20 ya 30 kilo"), set quantity to null. Set to null if not specified or production_status is "none".
- Preserve an explicitly stated negative quantity, including its minus sign; do not turn "-5 kilo" into positive 5.
- "unit": string or null. Standardize to "kg", "g", "bottle", "packet", or "jar". Standard default unit for achar is "kg". Set to null if production_status is "none" or quantity is null.
- If the quantity is ambiguous or unresolved, return both "quantity": null and "unit": null. Do not return the unit separately.

You must respond ONLY with the JSON object. Do not include any explanations, reasoning, or markdown code fences."""

ISSUE_EXTRACTION_SYSTEM_PROMPT = """You are an AI assistant for FarmDidi, an organization supporting rural women entrepreneurs (Didis) in India.
Your task is to extract issue information from a Didi's Hindi, Hinglish, or English message.

Output MUST be a single valid JSON object with exactly these keys:
- "has_issue": boolean
- "issue_type": string or null, one of ["inventory", "raw_material", "equipment", "production", "personal", "other", "unknown"]
- "issue": string or null
- "details": string or null

Use has_issue=false and null for the other fields when the Didi clearly says there is no issue, such as "Koi dikkat nahi hai" or "Sab theek hai".

Use has_issue=true for a reported problem. Normalize clear issues into simple English without inventing information:
- bottles kam hain / bottle kam pad rahi hain -> issue_type "inventory", issue "Bottle shortage"
- raw material nahi mila / maal nahi aaya -> issue_type "raw_material"
- machine kharab hai -> issue_type "equipment", issue "Machine problem"
- production mein dikkat hai -> issue_type "production"
- tabiyat kharab hai -> issue_type "personal"

For a vague problem such as "Thoda problem hai", use issue_type "unknown", issue null, and details "Didi reported a problem but did not specify it".
For unrelated or unclear input such as "hello", use has_issue=true, issue_type "unknown", issue null, and details "Didi reported a problem but did not specify it". Do not invent an issue.
Do not invent quantities, severity, missing supplies, or required actions. Include details only when supported by the message, such as "Only 30 bottles available" for "Sirf 30 bottles bachi hain".

You must respond ONLY with the JSON object. Do not include explanations, reasoning, or markdown code fences."""

CORRECTION_EXTRACTION_SYSTEM_PROMPT = """You update an existing FarmDidi check-in from a Didi's natural-language correction.
Return one JSON object with exactly two complete nested objects: "production" and "issue".
Preserve every existing field unless the correction clearly changes it. Never invent values.
If the correction does not clearly specify any changed field, return the current objects unchanged.

The production object must contain production_status, product, quantity, and unit.
The issue object must contain has_issue, issue_type, issue, and details.
If the correction changes only quantity, preserve the existing product, status, unit, and issue object.
If the correction changes only an issue, preserve the complete production object.
Use null only when the existing value is null or the Didi explicitly removes a value.
Return JSON only, with no reasoning or markdown."""

AMBIGUOUS_QUANTITY_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:ya|or|-)\s*\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
NEGATIVE_QUANTITY_PATTERN = re.compile(r"(?<!\d)-\s*\d+(?:\.\d+)?\b")


def parse_production_message(message: str) -> ProductionUpdate:
    """
    Extract structured production update from natural language text using Groq LLM.
    Guarantees no reasoning leakage and returns a validated ProductionUpdate instance.
    """
    client = _get_client()

    kwargs = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": PRODUCTION_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": message.strip()},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
        "temperature": 0,
    }

    # Suppress reasoning leakage for reasoning models like Qwen
    if "qwen" in GROQ_MODEL.lower():
        kwargs["reasoning_effort"] = "none"

    response = client.chat.completions.create(**kwargs)
    raw_content = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as err:
        logger.error(f"Failed to decode LLM response as JSON: {raw_content}")
        raise ValueError(f"LLM returned invalid JSON: {raw_content}") from err

    # Normalize numeric quantity
    qty = data.get("quantity")
    if qty is not None:
        try:
            qty = float(qty)
        except (ValueError, TypeError):
            qty = None

    if qty is not None and qty >= 0 and NEGATIVE_QUANTITY_PATTERN.search(message):
        qty = -abs(qty)

    if qty is None and AMBIGUOUS_QUANTITY_PATTERN.search(message):
        data["unit"] = None

    return ProductionUpdate(
        production_status=data.get("production_status", "unclear"),
        product=data.get("product"),
        quantity=qty,
        unit=data.get("unit"),
    )


def parse_issue_message(message: str) -> IssueUpdate:
    """
    Extract structured issue information from a Didi's message using Groq.
    Returns a validated IssueUpdate instance without inventing missing details.
    """
    client = _get_client()

    kwargs = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": ISSUE_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": message.strip()},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
        "temperature": 0,
    }

    if "qwen" in GROQ_MODEL.lower():
        kwargs["reasoning_effort"] = "none"

    response = client.chat.completions.create(**kwargs)
    raw_content = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as err:
        logger.error("Failed to decode issue LLM response as JSON: %s", raw_content)
        raise ValueError(f"LLM returned invalid JSON: {raw_content}") from err

    return IssueUpdate(
        has_issue=data.get("has_issue", True),
        issue_type=data.get("issue_type"),
        issue=data.get("issue"),
        details=data.get("details"),
    )


def parse_correction_message(
    message: str,
    production: ProductionUpdate,
    issue: IssueUpdate,
) -> tuple[ProductionUpdate, IssueUpdate]:
    """Return candidate full production and issue snapshots for a correction."""
    client = _get_client()
    current = {
        "production": production.model_dump(),
        "issue": issue.model_dump(),
    }
    kwargs = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": CORRECTION_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Current check-in:\n{json.dumps(current)}\n\nCorrection:\n{message.strip()}",
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 400,
        "temperature": 0,
    }
    if "qwen" in GROQ_MODEL.lower():
        kwargs["reasoning_effort"] = "none"

    response = client.chat.completions.create(**kwargs)
    raw_content = response.choices[0].message.content.strip()
    try:
        data = json.loads(raw_content)
        return (
            ProductionUpdate(**data["production"]),
            IssueUpdate(**data["issue"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as err:
        logger.error("Failed to parse correction response: %s", raw_content)
        raise ValueError("LLM returned an invalid correction.") from err
