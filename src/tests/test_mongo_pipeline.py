from pymongo import MongoClient
from src.repository.noSQL import DocumentSurveySource  # the general adapter
from src.pipeline import run_pipeline

# --- Connect to MongoDB (still using Mongo for testing) ---
client = MongoClient("mongodb://localhost:27017")
db = client["thesis_pipeline"]

# --- Create the generic document adapter ---
source = DocumentSurveySource(
    template_collection=db.surveys,
    response_collection=db.responses,
    flags_collection=db.flags
)

# --- Run your pipeline ---
rules_path = "src/rules/pii_patterns.json"
output = run_pipeline(source, survey_id="survey1", rules_path=rules_path)

# --- Print results ---
if output.get("results"):
    print("\nFlagged PII results:")
    for res in output["results"]:
        print(res)
else:
    print("No results found.")
