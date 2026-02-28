# test_pipeline.py
"""
Unified pipeline test
lets pray this one actually works
"""

import argparse
import sys

# Configuration: edit these if your connection details change
MONGO_URI       = "mongodb://localhost:27017"
MONGO_DB        = "thesis_pipeline"
SURVEY_ID       = "survey1"

SQL_CONN        = "postgresql://thesis:thesis@localhost:5432/thesis_pipeline"
SQL_TABLES      = {
    "templates": "survey_templates",
    "responses": "survey_responses",
    "flags":     "pii_flags",
}

FILE_DATASET    = "src/tests/test_dataset"
FILE_OUTPUT     = "src/tests/test_dataset/anonymized_output.json"

RULES_PATH      = "src/rules/pii_patterns.json"

# source builders
def build_mongo_source():
    from pymongo import MongoClient
    from src.repository.noSQL import DocumentSurveySource

    client = MongoClient(MONGO_URI)
    db     = client[MONGO_DB]

    source = DocumentSurveySource(
        template_collection=db.surveys,
        response_collection=db.responses,
        flags_collection=db.flags,
    )
    return source, db   # return db so the caller can print results


def build_sql_source():
    from src.repository.sql_source import SQLSurveySource
    from sqlalchemy import create_engine

    source = SQLSurveySource(SQL_CONN, SQL_TABLES)
    engine = create_engine(SQL_CONN)
    return source, engine


def build_file_source():
    from pathlib import Path
    from src.repository.file_source import FileSurveySource

    source = FileSurveySource(FILE_DATASET)
    return source, None

# pipeline builders
def build_pipeline(backend: str, source, detector, extra):
    from src.anonymization.run_pipeline import (
        DocumentAnonymizationPipeline,
        SQLAnonymizationPipeline,
        FileAnonymizationPipeline,
    )

    if backend == "mongo":
        db = extra
        return DocumentAnonymizationPipeline(
            source=source,
            detector=detector,
            output_collection=db.responses_anonymized,
        )

    if backend == "sql":
        engine = extra
        return SQLAnonymizationPipeline(
            source=source,
            detector=detector,
            engine=engine,
            output_table="survey_responses_anonymized",
        )

    if backend == "file":
        return FileAnonymizationPipeline(
            source=source,
            detector=detector,
            output_path=FILE_OUTPUT,
        )

    raise ValueError(f"Unknown backend: {backend!r}")

# results
def print_mongo_results(db, survey_id: str):
    print("\n  Anonymized records (MongoDB → responses_anonymized):")
    for record in db.responses_anonymized.find({"survey_id": survey_id}):
        print(f"    Respondent {record['_id']}:")
        for qid, val in record.get("answers", {}).items():
            print(f"      {qid}: {val!r}")

    print("\n  Audit log (MongoDB → flags):")
    for flag in db.flags.find({"survey_id": survey_id}):
        flag.pop("_id", None)
        print(f"    {flag}")


def print_sql_results(engine, survey_id: str):
    from sqlalchemy import text
    print("\n  Anonymized records (Postgres → survey_responses_anonymized):")
    with engine.connect() as conn:
        try:
            rows = conn.execute(
                text("SELECT * FROM survey_responses_anonymized WHERE survey_id=:sid"),
                {"sid": survey_id},
            ).fetchall()
            for row in rows:
                print(f"    {dict(row._mapping)}")
        except Exception as e:
            print(f"    (could not query output table: {e})")


def print_file_results():
    import json
    from pathlib import Path
    path = Path(FILE_OUTPUT)
    if not path.exists():
        print("  (output file not found)")
        return
    print(f"\n  Anonymized records (file → {FILE_OUTPUT}):")
    records = json.loads(path.read_text())
    for record in records:
        print(f"    Respondent {record['respondent_id']}:")
        for qid, val in record.get("answers", {}).items():
            print(f"      {qid}: {val!r}")


def pick_backend() -> str:
    print("\n  Select a data source backend:")
    print("    1) MongoDB  (NoSQL)")
    print("    2) SQL      (Postgres)")
    print("    3) File     (JSON)")
    while True:
        choice = input("\n  Enter 1, 2, or 3: ").strip()
        if choice == "1":
            return "mongo"
        if choice == "2":
            return "sql"
        if choice == "3":
            return "file"
        print("  Invalid choice, try again.")


def main():
    parser = argparse.ArgumentParser(description="Unified anonymization pipeline test")
    parser.add_argument(
        "--source", choices=["mongo", "sql", "file"],
        help="Backend to use (skips interactive prompt)"
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="Skip interactive strategy confirmation and use recommended strategies"
    )
    args = parser.parse_args()

    backend    = args.source or pick_backend()
    do_confirm = not args.no_confirm

    print(f"\n  Backend: {backend.upper()}")
    print(f"  Interactive confirm: {'yes' if do_confirm else 'no (using recommendations)'}")

    # building source and detectors
    from src.anonymization.detector import PIIDetector

    detector = PIIDetector(patterns_path=RULES_PATH)

    if backend == "mongo":
        source, extra = build_mongo_source()
        survey_id     = SURVEY_ID
    elif backend == "sql":
        source, extra = build_sql_source()
        survey_id     = SURVEY_ID
    else:
        source, extra = build_file_source()
        survey_id     = None   # file source ignores survey_id

    # building our pipeline here
    pipeline = build_pipeline(backend, source, detector, extra)

    print("\n  Running PII detection...")
    analysis = pipeline.detect(survey_id)

    if not analysis:
        print("  No fields found. Is the survey seeded?")
        sys.exit(0)

    pipeline.review(analysis)

    if do_confirm:
        confirmed = pipeline.confirm(analysis)
    else:
        # Auto accept all recommendations
        confirmed = [dict(f, chosen_strategy=f["recommended_strategy"]) for f in analysis]
        print("  Using recommended strategies (--no-confirm).")

    print("\n  Applying anonymization...")
    pipeline.run(survey_id, confirmed)

    if backend == "mongo":
        print_mongo_results(extra, SURVEY_ID)
    elif backend == "sql":
        print_sql_results(extra, SURVEY_ID)
    else:
        print_file_results()

    print("\n  Pipeline complete.\n")


if __name__ == "__main__":
    main()