# src/anonymization/anonymization_pipeline.py
from typing import List
from src.anonymization.anonymizer import anonymize_field

class AnonymizationPipeline:
    def __init__(self, source, detector):
        """
        :param source: An adapter implementing iter_records() and save_record()
        :param detector: Your existing detector instance
        """
        self.source = source
        self.detector = detector

    def anonymize_record(self, record: dict) -> dict:
        """Anonymize a single record based on detected PII fields."""
        record = record.copy()
        answers = record.get("answers", {})

        pii_fields = self.detector.detect_pii(answers)  # now pass answers dict

        for field in pii_fields:
            if field in answers:
                answers[field] = anonymize_field(field, answers[field])

        record["answers"] = answers
        return record

    def run(self):
        """Iterate through all records in the source and anonymize them."""
        for record in self.source.iter_records():
            anon_record = self.anonymize_record(record)
            self.source.save_record(record["id"], anon_record)
