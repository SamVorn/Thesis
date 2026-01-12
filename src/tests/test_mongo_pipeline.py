from pymongo import MongoClient
from src.repository.mongo_source import MongoDataSource
from src.pipeline import run_pipeline

client = MongoClient("mongodb://localhost:27017")
db = client["thesis_pipeline"]

# Pass the full db, not just one collection
mongo_source = MongoDataSource(db)

rules_path = "src/rules/pii_patterns.json"

output = run_pipeline(mongo_source, survey_id="survey1", rules_path=rules_path)

if output.get("results"):
    print("\nFlagged PII results:")
    for res in output["results"]:
        print(res)
else:
    print("No results found.")
