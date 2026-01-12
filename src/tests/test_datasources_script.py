# test_data_sources.py
import json
from pathlib import Path
from types import SimpleNamespace

from repository.file_source import FileDataSource
from repository.mongo_source import MongoDataSource
from repository.sql_source import SQLDataSource

# -------------------------
# 1. Setup dummy FileDataSource
# -------------------------
dummy_dir = Path("./dummy_dataset")
dummy_dir.mkdir(exist_ok=True)

# Create a dummy template file
template_path = dummy_dir / "survey1_template.json"
with open(template_path, "w", encoding="utf-8") as f:
    json.dump({"title": "Dummy Survey"}, f)

# Create a dummy response file
response_path = dummy_dir / "response1.json"
with open(response_path, "w", encoding="utf-8") as f:
    json.dump({"survey_id": "survey1", "respondent_id": "r1", "answers": {"q1": "yes"}}, f)

file_source = FileDataSource(str(dummy_dir))

# -------------------------
# 2. Setup dummy MongoDataSource
# -------------------------
class DummyCollection:
    """Simulate a pymongo Collection"""
    def __init__(self):
        self.data = [
            {"_id": "m1", "survey_id": "survey1", "answers": {"q1": "no"}, "template": {"title": "Mongo Survey"}}
        ]
    
    def find(self, query):
        return [doc for doc in self.data if doc.get("survey_id") == query.get("survey_id")]
    
    def find_one(self, query):
        results = self.find(query)
        return results[0] if results else None

mongo_source = MongoDataSource(DummyCollection())

# -------------------------
# 3. Setup dummy SQLDataSource
# -------------------------
import sqlite3

conn = sqlite3.connect(":memory:")
cursor = conn.cursor()
cursor.execute("CREATE TABLE survey_templates (survey_id TEXT, template_json TEXT)")
cursor.execute("CREATE TABLE survey_responses (survey_id TEXT, respondent_id TEXT, answers_json TEXT)")

cursor.execute("INSERT INTO survey_templates VALUES (?, ?)", ("survey1", json.dumps({"title": "SQL Survey"})))
cursor.execute("INSERT INTO survey_responses VALUES (?, ?, ?)", ("survey1", "s1", json.dumps({"q1": "maybe"})))
conn.commit()

sql_source = SQLDataSource(conn)

# -------------------------
# 4. Test function for any source
# -------------------------
def test_source(source, survey_id="survey1"):
    print(f"\nTesting {source.__class__.__name__}")
    
    template = source.get_survey_template(survey_id)
    print("Template:", template)
    
    print("Responses:")
    for response in source.iter_responses(survey_id):
        print(response)

# -------------------------
# 5. Run tests
# -------------------------
for source in [file_source, mongo_source, sql_source]:
    test_source(source)
