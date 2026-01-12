from typing import Dict, Generator
from .interface import SurveyDataSource
import sqlite3  # assuming you’re using sqlite, adjust for other DBs

class SQLDataSource(SurveyDataSource):
    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    def get_survey_template(self, survey_id: str) -> Dict | None:
        # Example: fetch template from a table 'survey_templates'
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT template_json FROM survey_templates WHERE survey_id = ?",
            (survey_id,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def iter_responses(self, survey_id: str) -> Generator[Dict, None, None]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT respondent_id, answers_json FROM survey_responses WHERE survey_id = ?",
            (survey_id,)
        )
        for row in cursor.fetchall():
            yield {
                "respondent_id": row[0],
                "answers": row[1]  # assuming stored as JSON string/dict
            }
