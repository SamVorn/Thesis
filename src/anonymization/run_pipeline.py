# src/anonymization/run_pipeline.py

from src.anonymization.anonymization_pipeline import AnonymizationPipeline
from src.anonymization.anonymizer import STRATEGY_NONE, apply_strategy
import json
from pathlib import Path



# NoSQL Document stuff (Mongo)
class DocumentAnonymizationPipeline(AnonymizationPipeline):
    """
    Anonymize survey responses stored in a document DB.
    Writes anonymized records and detection results to detector-specific
    collections so regex, ai, and hybrid runs never overwrite each other.

    Collections written:
      responses_anonymized_<detector>   — anonymized survey responses
      detection_results                 — field-level detection + strategy output
    """

    def __init__(self, source, detector, db):
        super().__init__(source, detector)
        self.db = db  # pymongo Database handle

    def run(self, survey_id: str = None, confirmed_analysis: list = None) -> list:
        records = super().run(survey_id, confirmed_analysis)

        detector_type     = self._detector_type()
        collection_name   = f"responses_anonymized_{detector_type}"
        target_collection = self.db[collection_name]

        for record in records:
            target_collection.replace_one(
                {"_id": record["respondent_id"], "survey_id": survey_id},
                {
                    "_id":           record["respondent_id"],
                    "survey_id":     survey_id,
                    "detector_type": detector_type,
                    "answers":       record["answers"],
                },
                upsert=True,
            )

        print(f"  Anonymized records saved → MongoDB:{collection_name} "
              f"(survey={survey_id}, detector={detector_type})")

        return records

    def save_detection_results(self, survey_id: str, confirmed_analysis: list) -> None:
        doc = self._build_results_document(survey_id, confirmed_analysis)

        self.db["detection_results"].replace_one(
            {
                "survey_id":     doc["survey_id"],
                "detector_type": doc["detector_type"],
            },
            doc,
            upsert=True,
        )
        print(f"  Detection results saved → MongoDB:detection_results "
              f"(survey={survey_id}, detector={doc['detector_type']})")

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

        # UPDATED: write to a detector-specific table so results from
        # regex, ai, and hybrid runs are stored separately.
        # Tables: survey_responses_anonymized_regex,
        #         survey_responses_anonymized_ai,
        #         survey_responses_anonymized_hybrid
        detector_type = self._detector_type()
        output_table  = f"{self.output_table}_{detector_type}"

        upsert_sql = f"""
            INSERT INTO {output_table} (respondent_id, survey_id, answers_json)
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

        print(f"  Anonymized records saved → Postgres:{output_table} "
              f"(survey={survey_id}, detector={detector_type})")

        return records

    # ADDED: writes the detection results document to the "detection_results" SQL table
    # upserts on (survey_id, detector_type) so re-runs overwrite rather than duplicate
    # requires the detection_results table — see sql_schema.sql for the CREATE TABLE statement
    def save_detection_results(self, survey_id: str, confirmed_analysis: list) -> None:
        from sqlalchemy import text as sa_text

        doc = self._build_results_document(survey_id, confirmed_analysis)

        upsert_sql = """
            INSERT INTO detection_results (survey_id, detector_type, result_json)
            VALUES (:survey_id, :detector_type, :result_json)
            ON CONFLICT (survey_id, detector_type)
            DO UPDATE SET result_json = EXCLUDED.result_json
        """

        with self.engine.begin() as conn:
            conn.execute(sa_text(upsert_sql), {
                "survey_id":     doc["survey_id"],
                "detector_type": doc["detector_type"],
                "result_json":   json.dumps(doc),
            })

        print(f"  Detection results saved → Postgres:detection_results "
              f"(survey={survey_id}, detector={doc['detector_type']})")

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

        # UPDATED: write to a detector-specific file so results from
        # regex, ai, and hybrid runs are stored separately.
        # Files: anonymized_output_regex.json, anonymized_output_ai.json,
        #        anonymized_output_hybrid.json
        detector_type = self._detector_type()
        output_path   = self.output_path.parent / f"anonymized_output_{detector_type}.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)

        print(f"  Anonymized records saved → {output_path}")
        return records

    # ADDED: writes the detection results document to a JSON file in the same folder
    # as the anonymized output, named "detection_results_<detector_type>.json"
    # allows multiple detector runs to coexist without overwriting each other
    def save_detection_results(self, survey_id: str, confirmed_analysis: list) -> None:
        doc = self._build_results_document(survey_id, confirmed_analysis)

        results_path = self.output_path.parent / f"detection_results_{doc['detector_type']}.json"
        results_path.parent.mkdir(parents=True, exist_ok=True)

        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)

        print(f"  Detection results saved → {results_path}")