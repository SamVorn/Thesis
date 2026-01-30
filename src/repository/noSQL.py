from typing import Dict, Generator
from .interface import SurveyDataSource
"""
noSQL.py
Fully generic document-based NoSQL adapter for the survey pipeline.
Works with MongoDB, DynamoDB, CouchDB, Firestore, or any document store
implementing find_one, find, and insert_many methods.
"""

class DocumentSurveySource(SurveyDataSource):

    def __init__(self, template_collection, response_collection, flags_collection=None):
        self.templates = template_collection
        self.responses = response_collection
        self.flags = flags_collection

    def get_survey_template(self, survey_id: str) -> Dict | None:
        return self.templates.find_one({"survey_id": survey_id})

    def iter_responses(self, survey_id: str) -> Generator[Dict, None, None]:
        for r in self.responses.find({"survey_id": survey_id}):
            yield {
                # normalization 
                "respondent_id": r.get("_id"),  
                "answers": r.get("answers", {})  
            }

    def save_flags(self, survey_id: str, flagged_data):
        if flagged_data and self.flags:
            self.flags.insert_many(flagged_data)
