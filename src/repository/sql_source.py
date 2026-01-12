from sqlalchemy import create_engine, text
from .interface import SurveyDataSource

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
        query = f"SELECT * FROM {self.tables['templates']} WHERE survey_id=:survey_id"
        with self.engine.connect() as conn:
            result = conn.execute(text(query), {"survey_id": survey_id}).first()
            return dict(result) if result else None

    def iter_responses(self, survey_id: str):
        query = f"SELECT * FROM {self.tables['responses']} WHERE survey_id=:survey_id"
        with self.engine.connect() as conn:
            for row in conn.execute(text(query), {"survey_id": survey_id}):
                yield dict(row)

    def save_flags(self, survey_id: str, flagged_data):
        query = f"INSERT INTO {self.tables['flags']} (survey_id, data) VALUES (:survey_id, :data)"
        with self.engine.connect() as conn:
            for f in flagged_data:
                conn.execute(text(query), {"survey_id": survey_id, "data": str(f)})
