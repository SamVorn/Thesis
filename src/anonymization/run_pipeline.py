# src/anonymization/run_pipeline.py

from src.anonymization.anonymization_pipeline import AnonymizationPipeline
from src.anonymization.anonymizer import STRATEGY_NONE, apply_strategy
import json
from pathlib import Path



# NoSQL Document stuff (Mongo)
class DocumentAnonymizationPipeline(AnonymizationPipeline):
    """
    Objective:
    Anonymize survey responses stored in a document DB
    write results to a separate output collection
    """

    def __init__(self, source, detector, output_collection):
        super().__init__(source, detector)
        self.output_collection = output_collection

    def run(self, survey_id: str = None, confirmed_analysis: list = None) -> list:
        # anonymize and insert records into the output collection
        records = super().run(survey_id, confirmed_analysis)

        for record in records:
            self.output_collection.replace_one(
                {"_id": record["respondent_id"], "survey_id": survey_id},
                {
                    "_id":       record["respondent_id"],
                    "survey_id": survey_id,
                    "answers":   record["answers"],
                },
                upsert=True,
            )

        return records

# SQL stuff
class SQLAnonymizationPipeline(AnonymizationPipeline):
    """
    Objective:
    Anonymize responses from SQL source
    write results back dedicated anonymized-responses table
    The target table must exist and have columns respondent_id TEXT, survey_id TEXT, answers_json JSONB/TEXT
    """

    def __init__(self, source, detector, engine, output_table: str):
        super().__init__(source, detector)
        self.engine       = engine
        self.output_table = output_table

    def run(self, survey_id: str = None, confirmed_analysis: list = None) -> list:
        from sqlalchemy import text as sa_text

        records = super().run(survey_id, confirmed_analysis)

        upsert_sql = f"""
            INSERT INTO {self.output_table} (respondent_id, survey_id, answers_json)
            VALUES (:respondent_id, :survey_id, :answers_json)
            ON CONFLICT (respondent_id, survey_id)
            DO UPDATE SET answers_json = EXCLUDED.answers_json
        """

        with self.engine.begin() as conn:
            for record in records:
                conn.execute(sa_text(upsert_sql), {
                    "respondent_id": record["respondent_id"],
                    "survey_id":     survey_id,
                    "answers_json":  json.dumps(record["answers"]),
                })

        return records

# file stuff
class FileAnonymizationPipeline(AnonymizationPipeline):
    """
    Objective: 
    Anonymize survey responses from JSON files
    write back anonymized to a JSON file alongside the original files
    """
    
    def __init__(self, source, detector, output_path: str):
        super().__init__(source, detector)
        self.output_path = Path(output_path)

    def run(self, survey_id: str = None, confirmed_analysis: list = None) -> list:
        records = super().run(survey_id, confirmed_analysis)

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

        print(f"  Anonymized records saved → {self.output_path}")
        return records