"""
Masking helpers for values that must never be shown or logged in full.

Anything the UI needs to *recognise* but not *reuse* — an Aadhaar last-4, a PAN
tail, an OTP destination — is rendered through these helpers. They are the only
sanctioned way to put such a value in a response, a log line or the UI.

Deliberately absent: any helper that returns the cleartext value. If a flow
legitimately needs the real value it must fetch it explicitly through a
privileged path, not through a formatting helper.
"""

import re


def _clean(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def mask_aadhaar(value) -> str:
    """
    ``XXXX XXXX 1234`` — the trailing 4 digits only.

    Aadhaar is never returned in full by any API. If the value is too short to
    mask safely, nothing is returned at all rather than a partial number.
    """
    digits = _clean(value)
    if len(digits) < 4 or not digits.isdigit():
        return ""
    return f"XXXX XXXX {digits[-4:]}"


def mask_pan(value) -> str:
    """
    ``ABCDE****F`` — first 5 and last 1 character, matching the PAN shape.

    PAN is ``[A-Z]{5}[0-9]{4}[A-Z]``. Anything that does not match is treated
    as an invalid value and masked as fully as possible.
    """
    raw = _clean(value)
    if len(raw) < 6:
        return ""
    return f"{raw[:5]}****{raw[-1]}"


def mask_farmer_card(value) -> str:
    """Government Farmer Card / ID — keep only a short tail."""
    raw = _clean(value)
    if len(raw) < 4:
        return ""
    return f"****{raw[-4:]}"


def mask_phone(value) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 4:
        return "****"
    return f"{digits[:2]}****{digits[-2:]}"


def mask_email(value) -> str:
    if not value or "@" not in str(value):
        return "****"
    local, _, domain = str(value).partition("@")
    head = local[:1] if local else ""
    return f"{head}***@{domain}"


def mask_generic(value) -> str:
    """Last-resort mask for an unexpected identifier shape."""
    raw = re.sub(r"\s+", "", str(value or ""))
    if not raw:
        return ""
    if len(raw) <= 4:
        return "*" * len(raw)
    return f"{'*' * (len(raw) - 4)}{raw[-4:]}"
