"""
Shariah compliance screen: classifies each stock's business activity using
Gemini against standard industry-based Islamic finance screening criteria.
This is a BUSINESS-ACTIVITY screen only — it reads what a company does from
its description, not its financial ratios (debt-to-assets, interest income
share, etc.), which real Shariah screens also check and we don't have data
for. Ambiguous cases (financial holding companies, conglomerates) come back
"unclear" rather than a guess — treat those as needing a closer look, not as
compliant by default.

Not a substitute for a qualified scholar's ruling. It's a first-pass filter,
not a fatwa.
"""
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.core.config import get_settings
from app.models.db_models import Stock

MODEL_NAME = "gemini-3.5-flash"


class ShariahLLMOutput(BaseModel):
    status: Literal["compliant", "non_compliant", "unclear"]
    reason: str


class ShariahCheckError(Exception):
    pass


def _get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ShariahCheckError("GEMINI_API_KEY is not set — check your .env file.")
    return genai.Client(api_key=settings.gemini_api_key)


def _build_prompt(stock: Stock) -> str:
    description = (stock.business_description or "No description available.")[:800]
    return f"""
You are screening an EGX-listed company for Shariah compliance using standard
industry-based Islamic finance screening criteria. This is a BUSINESS-ACTIVITY
screen, not a scholarly ruling — you're classifying what the company does,
not issuing a fatwa.

Automatically non-compliant activities: conventional interest-based banking
or insurance, alcohol production or sale, gambling/casinos, pork products,
adult entertainment, conventional weapons manufactured for general civilian
sale.

Typically compliant: manufacturing, telecom, real estate development, food
production (non-alcohol/non-pork), technology, utilities, logistics,
healthcare, construction.

Mark "unclear" — do NOT guess — for: financial holding companies with mixed
business lines, conglomerates spanning both compliant and non-compliant
segments, or any case where a proper screen would also need financial ratios
(debt-to-assets, interest income share) that aren't in the description below.
Treating "unclear" as compliant by default would defeat the purpose of this
filter — when genuinely unsure, say so.

Company: {stock.ticker} — {stock.company_name}
Sector: {stock.sector or "unknown"}
Business description: {description}

Respond with a status (compliant, non_compliant, or unclear) and a 1-2
sentence reason grounded only in the description above.
""".strip()


def classify_stock(stock: Stock) -> ShariahLLMOutput:
    client = _get_client()
    prompt = _build_prompt(stock)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ShariahLLMOutput,
            ),
        )
    except Exception as e:  # noqa: BLE001
        raise ShariahCheckError(f"Gemini request failed for {stock.ticker}: {e}") from e

    parsed: ShariahLLMOutput | None = response.parsed
    if parsed is None:
        raise ShariahCheckError(
            f"Gemini didn't return valid structured output for {stock.ticker}. Raw: {response.text}"
        )

    return parsed