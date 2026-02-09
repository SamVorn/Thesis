# src/tests/test_sql_pipeline.py

from src.repository.sql_source import SQLSurveySource
from src.pipeline import run_pipeline

# SQLAlchemy connection string for Postgres
connection_string = "postgresql://thesis:thesis@localhost:5432/thesis_pipeline"

tables = {
    "templates": "survey_templates",
    "responses": "survey_responses",
    "flags": "pii_flags"
}

source = SQLSurveySource(connection_string, tables)

rules_path = "src/rules/pii_patterns.json"

output = run_pipeline(source, survey_id="survey1", rules_path=rules_path)

if output.get("results"):
    print("\nFlagged PII results:")
    for res in output["results"]:
        print(res)
else:
    print("No results found.")
