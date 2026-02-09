# src/tests/test_file_pipeline.py

from pathlib import Path
from src.repository.file_source import FileSurveySource
from src.pipeline import run_pipeline


# Path to your folder containing JSON survey files
dataset_folder = Path("src/tests/test_dataset")

# Initialize the file-based data source
source = FileSurveySource(dataset_folder)

# Path to your PII rules JSON
rules_path = "src/rules/pii_patterns.json"

# Run the pipeline (survey_id is intentionally omitted)
output = run_pipeline(source, rules_path=rules_path)

if not output or not output.get("results"):
    print("No results found.")
else:
    print("\nFlagged PII results:")
    for res in output["results"]:
        print(res)

    source.save_flags(None, output["results"])
    print("\nFlags saved to file.")
