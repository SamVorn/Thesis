# from pymongo import MongoClient
# from src.repository.noSQL import DocumentSurveySource  # the general adapter
# # check why using general adapter rather than the noSQL adapter
# from src.pipeline import run_pipeline

# # using mongodb for testing
# client = MongoClient("mongodb://localhost:27017")
# db = client["thesis_pipeline"]

# #creating the adapter
# source = DocumentSurveySource(
#     template_collection=db.surveys,
#     response_collection=db.responses,
#     flags_collection=db.flags
# )

# #run pipeline
# rules_path = "src/rules/pii_patterns.json"
# output = run_pipeline(source, survey_id="survey1", rules_path=rules_path)

# if output.get("results"):
#     print("\nFlagged PII results:")
#     for res in output["results"]:
#         print(res)
# else:
#     print("No results found.")
# test_mongo_pipeline_anonymization.py
from pymongo import MongoClient
from src.repository.noSQL import DocumentSurveySource
from src.anonymization.run_pipeline import DocumentAnonymizationPipeline
from src.anonymization.detector import SimpleDetector

# Setup MongoDB
client = MongoClient("mongodb://localhost:27017")
db = client["thesis_pipeline"]

# Adapter
source = DocumentSurveySource(
    template_collection=db.surveys,
    response_collection=db.responses,
    flags_collection=db.flags
)

# Collection to store anonymized responses
anon_collection = db.responses_anonymized

# Setup detector
detector = SimpleDetector()

# Initialize pipeline
pipeline = DocumentAnonymizationPipeline(
    source=source,
    detector=detector,
    output_collection=anon_collection
)

# Run anonymization
survey_id = "survey1"
pipeline.run(survey_id)

# Print flagged results
print("\nFlagged PII results (anonymized):")
for record in anon_collection.find({"survey_id": survey_id}):
    flagged_fields = [k for k, v in record.get("answers", {}).items() if v is None]
    if flagged_fields:
        print(f"Respondent {record['_id']}: {flagged_fields}")

# Optional: Print raw flagged info from flags collection
print("\nAudit log from flags collection:")
for flag in db.flags.find({"survey_id": survey_id}):
    print(flag)



# needs work 