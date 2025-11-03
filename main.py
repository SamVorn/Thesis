from src.pipeline import run_pipeline
import json

if __name__ == "__main__":
    output = run_pipeline("data/sample_survey.json", "rules/pii_patterns.json")

    print(json.dumps(output, indent=2))
