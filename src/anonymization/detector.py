# src/anonymization/detector.py
class SimpleDetector:
    """
    A minimal PII detector for testing purposes.
    Detects any field with 'name', 'email', 'phone', or 'age'.
    """
    def detect_pii(self, record: dict):
        answers = record.get("answers", {})
        pii_fields = [k for k, v in answers.items() if any(x in k.lower() for x in ["name", "email", "phone", "age"])]
        return pii_fields
