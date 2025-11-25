from src.pipeline import run_pipeline
import json

if __name__ == "__main__":
    #JSON Testing Input
    #output = run_pipeline("data/sample_survey.json", "rules/pii_patterns.json")
    
    #CSV Testing Input
    #output = run_pipeline("data/sample_survey2.csv", "rules/pii_patterns.json")

    # XLSX Testing Input
    #output = run_pipeline("data/sample_survey3.xlsx", "rules/pii_patterns.json")

    # XML Testing Input
    output = run_pipeline("data/sample_survey4.xml", "rules/pii_patterns.json")

    # Need to add txt and yaml testing inputs
    print(json.dumps(output, indent=2))
