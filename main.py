# from src.pipeline import run_pipeline
# import json

# if __name__ == "__main__":
#     #JSON Testing Input
#     #output = run_pipeline("data/sample_survey.json", "rules/pii_patterns.json")
    
#     #CSV Testing Input
#     #output = run_pipeline("data/sample_survey2.csv", "rules/pii_patterns.json")

#     # XLSX Testing Input
#     #output = run_pipeline("data/sample_survey3.xlsx", "rules/pii_patterns.json")

#     # XML Testing Input
#     output = run_pipeline("data/sample_survey4.xml", "rules/pii_patterns.json")

#     # Need to add txt and yaml testing inputs
#     print(json.dumps(output, indent=2))


# from src.pipeline import run_pipeline
# import json
# import os
# from collections import Counter, defaultdict

# def run_dataset(dataset_dir: str, rules_path: str):
#     survey_outputs = []
#     pii_by_question = defaultdict(Counter)
#     pii_overall = Counter()

#     for filename in os.listdir(dataset_dir):
#         if not filename.endswith(".json"):
#             continue

#         output = run_pipeline(
#             os.path.join(dataset_dir, filename),
#             rules_path
#         )

#         survey_outputs.append(output)

#         # Aggregate results
#         for r in output["results"]:
#             qid = r["question_id"]
#             for flag in r["flags"]:
#                 pii_by_question[qid][flag] += 1
#                 pii_overall[flag] += 1

#     return {
#         "dataset_size": len(survey_outputs),
#         "pii_overall": dict(pii_overall),
#         "pii_by_question": {
#             qid: dict(counter)
#             for qid, counter in pii_by_question.items()
#         },
#         "surveys": survey_outputs
#     }


# if __name__ == "__main__":
#     output = run_dataset(
#         dataset_dir="test_dataset",
#         rules_path="rules/pii_patterns.json"
#     )

#     print(json.dumps(output, indent=2))
 
from src.repository.file_source import FileDataSource
from src.pipeline import run_pipeline

data_source = FileDataSource("test_dataset")

run_pipeline(
    data_source=data_source,
    survey_id="demographics_v1",
    rules_path="rules/pii_patterns.json"
)
