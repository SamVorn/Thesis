# test_file_pipeline.py
from src.repository.file_source import FileSurveySource
from src.pipeline import run_pipeline
from pathlib import Path

# Path to your folder containing JSON survey files
dataset_folder = Path("testdataset")

# Initialize the file-based data source
source = FileSurveySource(str(dataset_folder))

# Path to your PII rules JSON
rules_path = "src/rules/pii_patterns.json"

# Run the pipeline on survey1
output = run_pipeline(source, survey_id="survey1", rules_path=rules_path)

# Print results
if output.get("results"):
    print("\nFlagged PII results:")
    for res in output["results"]:
        print(res)
else:
    print("No results found.")

# Optionally, save flags back to the JSON file
source.save_flags("survey1", output.get("results", []))
print("\nFlags saved to file.")
