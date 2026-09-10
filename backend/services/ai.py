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

In multi-turn check-in conversations, messages may provide only partial details:
- If the message contains only a quantity and/or unit (e.g. "20", "20kg", "kg", "20 kilo", "bees kilo"), set "production_status": "planned", extract "quantity" and "unit", and set "product": null.
- If the message mentions only a product (e.g. "lemon", "aam ka achar", "nimbu"), set "production_status": "planned", extract "product", and set "quantity": null, "unit": null.
- If the message presents an ambiguous choice or alternative between multiple products (e.g. "me lemon or aam", "lemon ya aam", "aam ya nimbu"), set "production_status": "planned", and set "product" to the mentioned products joined by " or " (e.g. "Lemon Achar or Mango Achar"). Do NOT guess or pick just one.

Output MUST be a single valid JSON object with the following keys:
- "production_status": string, one of ["planned", "completed", "none", "unclear"]
    - "planned": if Didi states what she is making/plans to make (e.g. "banaungi", "banayenge", "bana rahe hain", "banana hai", or directly stating the product and quantity such as "Mirchi ka achar das kilo", or supplying partial quantity/product details)
    - "completed": if explicitly already completed/finished ("bana liya", "ban gaya", "taiyaar ho gaya")
    - "none": if no production today ("kuch nahi banaungi", "chhutti hai", "production nahi hai", "nahi banayenge")
    - "unclear": if the intent is completely unrelated, nonsensical, or cannot be understood
- "product": string or null. Use the standard catalog name when recognized (e.g. "Mango Achar", "Lemon Achar", "Chilli Achar", "Mixed Achar", "Garlic Achar"). Set to null if production_status is "none" or no product is mentioned. If a product is clearly mentioned but is not in the catalog, preserve its stated product name so Python validation can reject it as an invalid product; do not substitute a catalog product. If multiple products are mentioned as choices or alternatives, join them with " or ".
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
NO_PRODUCTION_PATTERN = re.compile(
    r"\b(?:koi production nahi|kuch nahi|nahi bana|chhutti|not producing|no production)\b",
    re.IGNORECASE,
)

PRODUCT_CATALOG_PATTERNS = [
    ("Lemon Achar", [r"\blemon\b", r"\bnimbu\b", r"\bneembu\b", r"\blimbu\b"]),
    ("Mango Achar", [r"\baam\b", r"\bmango\b"]),
    ("Chilli Achar", [r"\bchilli\b", r"\bchili\b", r"\bmirchi\b", r"\bmirch\b"]),
    ("Mixed Achar", [r"\bmixed\b", r"\bmix\b", r"\bsabzi\b"]),
    ("Garlic Achar", [r"\bgarlic\b", r"\blahsun\b", r"\blasun\b"]),
]

HINDI_NUMBER_WORDS = {
    "ek": 1.0, "do": 2.0, "teen": 3.0, "chaar": 4.0, "char": 4.0, "paanch": 5.0, "panch": 5.0,
    "chhah": 6.0, "che": 6.0, "saat": 7.0, "aath": 8.0, "nau": 9.0, "das": 10.0,
    "gyarah": 11.0, "barah": 12.0, "terah": 13.0, "chaudah": 14.0, "pandrah": 15.0,
    "solah": 16.0, "satrah": 17.0, "atharah": 18.0, "unnis": 19.0, "bees": 20.0,
    "pachees": 25.0, "tees": 30.0, "chalis": 40.0, "pachaas": 50.0,
}

UNIT_MAPPING = {
    "kg": "kg", "kilo": "kg", "kilos": "kg", "g": "g", "gram": "g", "grams": "g",
    "bottle": "bottle", "bottles": "bottle", "jar": "jar", "jars": "jar",
    "packet": "packet", "packets": "packet",
}


def detect_catalog_products(text: str) -> list[str]:
    """Detect mentioned catalog products in text, preserving order of first appearance."""
    text_lower = text.lower()
    positions = []
    for prod_name, patterns in PRODUCT_CATALOG_PATTERNS:
        earliest = None
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m and (earliest is None or m.start() < earliest):
                earliest = m.start()
        if earliest is not None:
            positions.append((earliest, prod_name))
    positions.sort()
    return [name for _, name in positions]


def extract_fallback_production(message: str) -> dict:
    """Deterministic fallback production extraction when LLM is unavailable or misses fields."""
    msg_clean = message.strip().lower()
    if NO_PRODUCTION_PATTERN.search(msg_clean):
        return {"production_status": "none", "product": None, "quantity": None, "unit": None}

    status = "planned"
    prods = detect_catalog_products(message)
    if len(prods) > 1 and re.search(r"\b(?:or|ya|/)\b", message, re.IGNORECASE):
        product = " or ".join(prods)
    elif len(prods) == 1:
        product = prods[0]
    else:
        product = None

    qty = None
    unit = None
    if AMBIGUOUS_QUANTITY_PATTERN.search(message):
        qty = None
        unit = None
    else:
        m_qty = re.search(r"(?<![a-zA-Z0-9])(-?\d+(?:\.\d+)?)\s*([a-zA-Z]+)?\b", message)
        if m_qty:
            try:
                qty = float(m_qty.group(1))
            except (ValueError, TypeError):
                pass
            if m_qty.group(2):
                u_str = m_qty.group(2).lower()
                unit = UNIT_MAPPING.get(u_str)
        else:
            for word, val in HINDI_NUMBER_WORDS.items():
                if re.search(r"\b" + word + r"\b", msg_clean):
                    qty = val
                    break

        if not unit:
            for u_token, u_std in UNIT_MAPPING.items():
                if re.search(r"\b" + u_token + r"\b", msg_clean):
                    unit = u_std
                    break

    if product is None and qty is None and unit is None:
        status = "unclear"

    return {"production_status": status, "product": product, "quantity": qty, "unit": unit}


def parse_production_message(message: str) -> ProductionUpdate:
    """
    Extract structured production update from natural language text using Groq LLM
    supplemented by deterministic Python validation for ambiguity and partial inputs.
    """
    data = None
    try:
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

        if "qwen" in GROQ_MODEL.lower():
            kwargs["reasoning_effort"] = "none"

        response = client.chat.completions.create(**kwargs)
        raw_content = response.choices[0].message.content.strip()
        data = json.loads(raw_content)
    except Exception as err:
        logger.warning("Groq production extraction failed (%s), using deterministic fallback.", err)
        data = extract_fallback_production(message)

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

    # ── Python deterministic enhancements for ambiguous products & partial turns ──
    detected_prods = detect_catalog_products(message)
    has_or = bool(re.search(r"\b(?:or|ya|/)\b", message, re.IGNORECASE))

    # If user mentioned multiple products as alternative choices (e.g. "lemon or aam"):
    # never guess just one; preserve ambiguity as "Lemon Achar or Mango Achar"
    if len(detected_prods) > 1 and has_or:
        data["product"] = " or ".join(detected_prods)
        data["production_status"] = "planned"
    elif data.get("product") is None and len(detected_prods) == 1:
        data["product"] = detected_prods[0]
        if data.get("production_status") in (None, "unclear"):
            data["production_status"] = "planned"

    # If quantity was missed by LLM on a standalone number message (e.g. "20", "20kg"):
    if qty is None and not AMBIGUOUS_QUANTITY_PATTERN.search(message):
        fallback_data = extract_fallback_production(message)
        if fallback_data["quantity"] is not None:
            qty = fallback_data["quantity"]
            if not data.get("unit") and fallback_data["unit"]:
                data["unit"] = fallback_data["unit"]
            if data.get("production_status") in (None, "unclear"):
                data["production_status"] = "planned"

    # If unit was missed by LLM on a standalone unit message (e.g. "kg", "kilo"):
    if data.get("unit") is None:
        fallback_data = extract_fallback_production(message)
        if fallback_data["unit"]:
            data["unit"] = fallback_data["unit"]
            if data.get("production_status") in (None, "unclear"):
                data["production_status"] = "planned"

    return ProductionUpdate(
        production_status=data.get("production_status", "unclear"),
        product=data.get("product"),
        quantity=qty,
        unit=data.get("unit"),
    )


def extract_fallback_issue(message: str) -> IssueUpdate:
    """Deterministic fallback for issue extraction on Groq failure."""
    msg_clean = message.strip().lower()
    no_issue_kw = ["nahi", "theek", "thik", "koi nahi", "sab accha", "all good", "no issue", "no problem", "koi dikkat nahi", "kuch nahi"]
    if any(kw in msg_clean for kw in no_issue_kw) and not any(p in msg_clean for p in ["kam", "kharab", "shortage", "dikkat hai", "problem hai"]):
        return IssueUpdate(has_issue=False)

    if any(w in msg_clean for w in ["bottle", "dabba", "jar", "packaging"]):
        return IssueUpdate(has_issue=True, issue_type="inventory", issue="Bottle shortage")
    if any(w in msg_clean for w in ["mirchi", "namak", "oil", "tel", "masala", "kaccha maal", "raw material"]):
        return IssueUpdate(has_issue=True, issue_type="raw_material", issue=message.strip())
    if any(w in msg_clean for w in ["machine", "mixer", "sealer"]):
        return IssueUpdate(has_issue=True, issue_type="equipment", issue="Machine problem")
    if any(w in msg_clean for w in ["tabiyat", "bimar", "chhutti"]):
        return IssueUpdate(has_issue=True, issue_type="personal", issue=message.strip())

    return IssueUpdate(has_issue=True, issue_type="other", issue=message.strip())


def extract_fallback_correction(
    message: str,
    production: ProductionUpdate,
    issue: IssueUpdate,
) -> tuple[ProductionUpdate, IssueUpdate]:
    """Deterministic fallback for correction parsing on Groq failure."""
    msg_clean = message.strip().lower()
    is_cancel = bool(re.search(r"\b(?:kuch\s+nhi|kuch\s+nahi|sorry|galti|cancel|rehne\s+do)\b", msg_clean))
    has_num = bool(re.search(r"\d", msg_clean) or any(re.search(r"\b" + w + r"\b", msg_clean) for w in HINDI_NUMBER_WORDS))
    has_prod = bool(detect_catalog_products(message))

    if is_cancel and not has_num and not has_prod:
        return (production, issue)

    prod_copy = production.model_copy()
    issue_copy = issue.model_copy()

    nums = re.findall(r"\b(\d+(?:\.\d+)?)\b", msg_clean)
    if nums:
        try:
            prod_copy.quantity = float(nums[-1])
        except (ValueError, TypeError):
            pass
    for word, val in HINDI_NUMBER_WORDS.items():
        if re.search(r"\b" + word + r"\b", msg_clean):
            prod_copy.quantity = val
            break

    for u_token, u_std in UNIT_MAPPING.items():
        if re.search(r"\b" + u_token + r"\b", msg_clean):
            prod_copy.unit = u_std
            break

    prods = detect_catalog_products(message)
    if prods:
        prod_copy.product = prods[-1]

    return (prod_copy, issue_copy)


def parse_issue_message(message: str) -> IssueUpdate:
    """
    Extract structured issue information from a Didi's message using Groq.
    Returns a validated IssueUpdate instance without inventing missing details.
    """
    try:
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
        data = json.loads(raw_content)
        return IssueUpdate(
            has_issue=data.get("has_issue", True),
            issue_type=data.get("issue_type"),
            issue=data.get("issue"),
            details=data.get("details"),
        )
    except Exception as err:
        logger.warning("Groq issue extraction failed (%s), using deterministic fallback.", err)
        return extract_fallback_issue(message)


def parse_correction_message(
    message: str,
    production: ProductionUpdate,
    issue: IssueUpdate,
) -> tuple[ProductionUpdate, IssueUpdate]:
    """Return candidate full production and issue snapshots for a correction."""
    try:
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
        data = json.loads(raw_content)
        return (
            ProductionUpdate(**data["production"]),
            IssueUpdate(**data["issue"]),
        )
    except Exception as err:
        logger.warning("Groq correction parsing failed (%s), using deterministic fallback.", err)
        return extract_fallback_correction(message, production, issue)
