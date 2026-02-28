from sqlalchemy import create_engine, text
from typing import Optional
from .interface import SurveyDataSource
import json
import re

SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

def _validate_table(name: str) -> str:
    if not SAFE_IDENTIFIER.match(name):
        raise ValueError(f"Invalid table name: {name!r}")
    return name


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
        # Validate all table names at construction time, not at query time
        self.tables = {k: _validate_table(v) for k, v in table_names.items()}

    def get_survey_template(self, survey_id: Optional[str] = None):
        query = f"SELECT template_json FROM {self.tables['templates']} WHERE survey_id=:survey_id"
        with self.engine.connect() as conn:
            result = conn.execute(text(query), {"survey_id": survey_id}).first()
            if not result:
                return None
            return json.loads(result.template_json) if isinstance(result.template_json, str) else result.template_json

    def iter_responses(self, survey_id: Optional[str] = None):
        query = f"SELECT * FROM {self.tables['responses']} WHERE survey_id=:survey_id"
        with self.engine.connect() as conn:
            for row in conn.execute(text(query), {"survey_id": survey_id}):
                r = dict(row._mapping)
                yield {
                    "respondent_id": r.get("respondent_id") or r.get("id"),
                    "answers": json.loads(r["answers_json"]) if isinstance(r.get("answers_json"), str) else r.get("answers_json")
                }

    def save_flags(self, survey_id: str, flagged_data):
        query = f"INSERT INTO {self.tables['flags']} (survey_id, data) VALUES (:survey_id, :data)"
        with self.engine.begin() as conn:
            for f in flagged_data:
                conn.execute(text(query), {"survey_id": survey_id, "data": json.dumps(f)})
            conn.commit()