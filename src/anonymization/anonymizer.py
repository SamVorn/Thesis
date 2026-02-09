# functions for anonymizing PII
# src/anonymization/anonymizer.py
import hashlib
import re

def anonymize_email(email: str) -> str:
    """Consistently pseudonymize emails."""
    if not email:
        return email
    hash_part = hashlib.sha256(email.encode()).hexdigest()[:16]
    return f"{hash_part}@anon.com"

def anonymize_name(name: str) -> str:
    """Pseudonymize names."""
    if not name:
        return name
    return "ANON_" + hashlib.sha1(name.encode()).hexdigest()[:8]

def anonymize_phone(phone: str) -> str:
    """Mask digits in phone numbers."""
    if not phone:
        return phone
    return re.sub(r"\d", "X", phone)

def anonymize_age(age: int) -> str:
    """Generalize age into age brackets."""
    if age is None:
        return None
    if age < 20:
        return "<20"
    elif age < 30:
        return "20-29"
    elif age < 40:
        return "30-39"
    else:
        return "40+"


def anonymize_field(field_name: str, value):
    """Dispatch to the correct anonymization function based on field name."""
    if value is None:
        return value

    field_name = field_name.lower()

    if "email" in field_name:
        return anonymize_email(value)
    elif "name" in field_name:
        return anonymize_name(value)
    elif "phone" in field_name:
        return anonymize_phone(value)
    elif "age" in field_name:
        return anonymize_age(value)
    
    # Default: suppress unknown PII
    return None
