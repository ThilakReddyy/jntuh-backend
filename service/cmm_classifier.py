"""Gemini-backed classifier for grace-marks CMM uploads."""

from __future__ import annotations

import mimetypes
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from config.settings import CMM_REFERENCE_PATH, GEMINI_API_KEY, GEMINI_MODEL

MAX_INLINE_BYTES = 19 * 1024 * 1024
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class CMMResult(BaseModel):
    classification: Literal["cmm", "not_cmm", "uncertain"] = Field(
        description="The document classification."
    )
    is_cmm: bool = Field(
        description="True only when classification is cmm; otherwise false."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the classification from 0.0 to 1.0.",
    )
    document_type: str = Field(description="Short name for the detected document type.")
    evidence: list[str] = Field(
        description="Visible features supporting the classification, without personal data."
    )
    missing_or_unclear: list[str] = Field(
        description="Expected CMM features that are missing or unreadable."
    )


PROMPT = """
You are a careful document classifier. Two documents follow this instruction:

1. REFERENCE DOCUMENT: a known example of a Consolidated Memorandum of Marks (CMM).
2. CANDIDATE DOCUMENT: the newly uploaded document to classify.

A CMM is a consolidated final academic marks record. It normally contains most of these semantic
features: an institution/university heading, student/program identifiers, results spanning multiple
semesters or academic years, subject-wise grades/marks/credits, and a final aggregate such as total
credits, marks, percentage, or CGPA. Layout and wording may differ by institution.

Classify the CANDIDATE, not the reference. Use the reference only to understand the document category.
Do not require an exact visual match or the same university. A single-semester marks sheet, degree
certificate, provisional certificate, transcript request, hall ticket, ID card, unrelated document,
or blank/illegible document is not a confirmed CMM. If the candidate is too cropped, blurry, or
ambiguous to verify the defining features, return "uncertain" rather than guessing.

IMPORTANT:
If the candidate says or clearly indicates "sample document", "sample", "not valid
for verification", "not valid for official use", "not for verification", or equivalent wording
showing that it is not an official/valid document, classify it as "not_cmm" even if it otherwise
looks like a CMM.

Set is_cmm=true only when classification="cmm". Do not include names, roll numbers, serial numbers,
barcodes, or other personal data in evidence. Keep evidence factual and concise.
"""


class CMMClassifierConfigurationError(RuntimeError):
    """Raised when the classifier cannot be configured safely."""


def _classify_cmm_sync(
    candidate_data: bytes,
    candidate_mime_type: str,
) -> CMMResult:
    if not GEMINI_API_KEY:
        raise CMMClassifierConfigurationError("GEMINI_API_KEY is not configured.")

    reference = CMM_REFERENCE_PATH
    if not reference.is_file():
        raise CMMClassifierConfigurationError(
            f"CMM reference document was not found at {reference}."
        )

    reference_mime_type, _ = mimetypes.guess_type(reference.name)
    if reference_mime_type not in SUPPORTED_MIME_TYPES:
        raise CMMClassifierConfigurationError(
            "The configured CMM reference has an unsupported file type."
        )

    reference_data = reference.read_bytes()
    if len(candidate_data) + len(reference_data) > MAX_INLINE_BYTES:
        raise ValueError(
            "Candidate and reference documents exceed Gemini's inline limit."
        )

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            PROMPT,
            "REFERENCE DOCUMENT:",
            types.Part.from_bytes(
                data=reference_data,
                mime_type=reference_mime_type,
            ),
            "CANDIDATE DOCUMENT:",
            types.Part.from_bytes(
                data=candidate_data,
                mime_type=candidate_mime_type,
            ),
        ],
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=CMMResult,
        ),
    )

    if response.parsed is not None:
        result = response.parsed
        if not isinstance(result, CMMResult):
            result = CMMResult.model_validate(result)
    elif response.text:
        result = CMMResult.model_validate_json(response.text)
    else:
        raise RuntimeError("Gemini returned no classification.")

    if result.is_cmm != (result.classification == "cmm"):
        raise RuntimeError("Gemini returned an inconsistent classification.")
    return result


async def classify_cmm_document(
    candidate_data: bytes,
    candidate_mime_type: str,
) -> CMMResult:
    """Classify bytes off the event loop because the Gemini SDK call is synchronous."""

    if candidate_mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError("Unsupported candidate document type.")
    return await run_in_threadpool(
        _classify_cmm_sync,
        candidate_data,
        candidate_mime_type,
    )
