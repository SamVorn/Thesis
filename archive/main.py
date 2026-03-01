# file is unnecessary for current state of project, but kept for possible future use
# used for testing basic pipeline functionality
from src.repository.file_source import FileDataSource
from src.pipeline import run_pipeline

data_source = FileDataSource("test_dataset")

run_pipeline(
    data_source=data_source,
    survey_id="demographics_v1",
    rules_path="rules/pii_patterns.json"
)
