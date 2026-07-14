# src/repository/noSQL.py

"""
noSQL.py
Generic document-based NoSQL adapter for the survey pipeline.
Compatible with MongoDB, DynamoDB, CouchDB, Firestore, or any document store
that exposes a find_one / find / insert_many style API.
"""
from typing import Dict, Generator, Optional
from .interface import SurveyDataSource

class DocumentSurveySource(SurveyDataSource):

    def __init__(self, template_collection, response_collection, flags_collection=None):
        self.templates = template_collection
        self.responses = response_collection
        self.flags = flags_collection

    def get_survey_template(self, survey_id: Optional[str] = None) -> Optional[Dict]:
        return self.templates.find_one({"survey_id": survey_id})

    def iter_responses(self, survey_id: Optional[str] = None) -> Generator[Dict, None, None]:
        for r in self.responses.find({"survey_id": survey_id}):
            yield {
                "respondent_id": r.get("_id"),
                "answers": r.get("answers", {})
            }

    def save_flags(self, survey_id: str, flagged_data):
        if flagged_data and self.flags is not None:
            self.flags.insert_many(flagged_data)