from typing import Dict, Generator
from .interface import SurveyDataSource
from pymongo.collection import Collection

class MongoDataSource(SurveyDataSource):
    def __init__(self, db):
        # Pass the full db instead of just one collection
        self.db = db

    def get_survey_template(self, survey_id):
        return self.db["surveys"].find_one({"survey_id": survey_id})

    def iter_responses(self, survey_id):
        cursor = self.db["responses"].find({"survey_id": survey_id})
        for doc in cursor:
            yield {
                "respondent_id": doc["_id"],
                "answers": doc["answers"]
            }
