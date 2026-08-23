"""Redaction helpers shared by the logging formatter and any handler that
might otherwise put student data into logs/Loki. See CLAUDE.md/SECURITY.md:
never log hall-ticket numbers, marks, student names, proof documents,
subscriptions, or admin values.
"""

import re

REDACTED = "[REDACTED]"

# Roll numbers are exactly 10 alphanumeric characters (see
# utils.helpers.validateRollNo). Over-redacting an unrelated 10-char token is
# an acceptable cost; missing a real roll number in a log line is not.
_ROLL_NUMBER_RE = re.compile(r"\b[0-9A-Za-z]{10}\b")

SENSITIVE_KEYS = {
    "htno",
    "hall_ticket",
    "hallticket",
    "roll_number",
    "rollno",
    "rollnumber",
    "marks",
    "sgpa",
    "cgpa",
    "subjects",
    "student_name",
    "name",
    "proof_url",
    "proof",
    "fcm_token",
    "subscription",
    "admin_key",
    "api_key",
}


def scrub_text(message: str) -> str:
    """Redact roll-number-shaped tokens from a free-form log message."""
    if not message:
        return message
    return _ROLL_NUMBER_RE.sub(REDACTED, message)


def scrub_mapping(data):
    """Recursively redact denylisted keys from a dict/list structure."""
    if isinstance(data, dict):
        return {
            k: REDACTED if str(k).lower() in SENSITIVE_KEYS else scrub_mapping(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [scrub_mapping(v) for v in data]
    return data
