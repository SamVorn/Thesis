from pymongo import MongoClient

# Connect to Docker MongoDB
client = MongoClient("mongodb://localhost:27017")
db = client["thesis_pipeline"]

# Drop collections to reset
db.drop_collection("surveys")
db.drop_collection("responses")

# Insert survey with questions at the top level
db["surveys"].insert_one({
    "survey_id": "survey1",
    "questions": [
        {"question_id": "q1", "text": "What is your name?"},
        {"question_id": "q2", "text": "What is your email?"}
    ]
})

# Insert some sample PII responses
db["responses"].insert_many([
    {"survey_id": "survey1", "answers": {"q1": "Alice Johnson", "q2": "alice@example.com"}},
    {"survey_id": "survey1", "answers": {"q1": "Bob Smith", "q2": "bob.smith@example.com"}}
])

print("MongoDB seeded successfully!")
