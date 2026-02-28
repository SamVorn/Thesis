# src/anonymization/anonymizer.py
import hashlib
import re

STRATEGY_SUPPRESS     = "suppress"
STRATEGY_PSEUDONYMIZE = "pseudonymize"
STRATEGY_GENERALIZE   = "generalize"
STRATEGY_NONE         = "none"


def anonymize_email(email: str) -> str:
    if not email:
        return email
    token = hashlib.sha256(email.encode()).hexdigest()[:16]
    return f"{token}@anon.com"


def anonymize_name(name: str) -> str:
    if not name:
        return name
    return "ANON_" + hashlib.sha1(name.encode()).hexdigest()[:8]


def anonymize_phone(phone: str) -> str:
    if not phone:
        return phone
    return re.sub(r"\d", "X", phone)


def anonymize_address(address: str) -> str:
    return "[ADDRESS REDACTED]" if address else address


# generalization 
def generalize_date(date_str: str) -> str:
    if not date_str:
        return date_str
    match = re.search(r"(\d{4})", str(date_str))
    return match.group(1) if match else "[DATE]"


def generalize_age(age) -> str:
    try:
        age = int(age)
    except (ValueError, TypeError):
        return str(age)
    for threshold, label in [(20, "<20"), (30, "20-29"), (40, "30-39"), (50, "40-49")]:
        if age < threshold:
            return label
    return "50+"


# labels to functions
_PSEUDONYMIZE_MAP = {
    "EMAIL":        anonymize_email,
    "PHONE":        anonymize_phone,
    "ADDRESS":      anonymize_address,
    "NAME_KEYWORD": anonymize_name,
}

_GENERALIZE_MAP = {
    "DATE": generalize_date,
}


def apply_strategy(field_name: str, value, strategy: str, detected_labels: list = None):
    """
    Objective:
    should apply the chosen anonymization strategy to a single field
    """
    if value is None or strategy == STRATEGY_NONE:
        return value

    if strategy == STRATEGY_SUPPRESS:
        return None

    labels = detected_labels or []

    if strategy == STRATEGY_PSEUDONYMIZE:
        for label in labels:
            fn = _PSEUDONYMIZE_MAP.get(label)
            if fn:
                return fn(str(value))
        # Generic fallback
        return "ANON_" + hashlib.sha256(str(value).encode()).hexdigest()[:12]

    if strategy == STRATEGY_GENERALIZE:
        for label in labels:
            fn = _GENERALIZE_MAP.get(label)
            if fn:
                return fn(str(value))
        # Fallback: first token + ellipsis
        parts = str(value).split()
        return (parts[0] + "...") if parts else value

    return value  # unknown strategy — leave unchanged