import json

def load_survey(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def load_rules(file_path):
    with open(file_path, "r") as f:
        return json.load(f)
