from src.pipeline import run_pipeline
import json

if __name__ == "__main__":
    output = run_pipeline("data/sample_survey.json", "rules/pii_patterns.json")
    # output = run_pipeline("data/sample_survey2.csv", "rules/pii_patterns.json")
    # both json and csv parsing work
    
    # output = run_pipeline("data/sample_survey3.xlsx", "rules/pii_patterns.json")
    # Work on xlsx parsing - does not work yet
    # output = run_pipeline("data/sample_survey4.xml", "rules/pii_patterns.json")
    # xml parsing does not work yet
    print(json.dumps(output, indent=2))
