from sqlalchemy import create_engine, text
from .interface import SurveyDataSource
import json

class SQLSurveySource(SurveyDataSource):
    def __init__(self, connection_string: str, table_names: dict):
        """
        table_names = {
            "templates": "templates_table",
            "responses": "responses_table",
            "flags": "flags_table"
        }
        """
        self.engine = create_engine(connection_string)
        self.tables = table_names

    def get_survey_template(self, survey_id: str):
        query = f"SELECT template_json FROM {self.tables['templates']} WHERE survey_id=:survey_id"
        with self.engine.connect() as conn:
            result = conn.execute(text(query), {"survey_id": survey_id}).first()
            if not result:
                return None
            return json.loads(result.template_json) if isinstance(result.template_json, str) else result.template_json

    def iter_responses(self, survey_id: str):
        query = f"SELECT * FROM {self.tables['responses']} WHERE survey_id=:survey_id"

        with self.engine.connect() as conn:
            for row in conn.execute(text(query), {"survey_id": survey_id}):
                # postgres
                r = dict(row._mapping)  

                yield {
                    "respondent_id": r.get("respondent_id") or r.get("id"),
                    "answers": json.loads(r["answers_json"]) if isinstance(r.get("answers_json"), str) else r.get("answers_json")
                }

    def save_flags(self, survey_id: str, flagged_data):
        query = f"INSERT INTO {self.tables['flags']} (survey_id, data) VALUES (:survey_id, :data)"
        with self.engine.connect() as conn:
            for f in flagged_data:
                conn.execute(text(query), {"survey_id": survey_id, "data": str(f)})
