# seed_sql.py
from sqlalchemy import create_engine, text
import json

# Connect to Postgres
engine = create_engine("postgresql://thesis:thesis@localhost:5432/thesis_pipeline")

# Survey template (list of dicts for pipeline compatibility)
template = {
    "survey_id": "survey1",
    "questions": [
        {"question_id": "q1", "text": "What is your full name?"},
        {"question_id": "q2", "text": "What is your email?"}
    ]
}

# Example survey responses
responses = [
    ("r1", "survey1", {"q1": "Alice Johnson", "q2": "alice@gmail.com"}),
    ("r2", "survey1", {"q1": "Bob Smith", "q2": "bob@yahoo.com"})
]

with engine.begin() as conn:
    # Clear tables for a fresh start
    conn.execute(text("DELETE FROM survey_templates"))
    conn.execute(text("DELETE FROM survey_responses"))
    conn.execute(text("DELETE FROM pii_flags"))

    # Insert survey template
    conn.execute(
        text("INSERT INTO survey_templates (survey_id, template_json) VALUES (:id, :data)"),
        {"id": "survey1", "data": json.dumps(template)}
    )

    # Insert responses
    for respondent_id, survey_id, answers in responses:
        conn.execute(
            text(
                "INSERT INTO survey_responses (respondent_id, survey_id, answers_json) "
                "VALUES (:r, :s, :a)"
            ),
            {"r": respondent_id, "s": survey_id, "a": json.dumps(answers)}
        )

print("Postgres database seeded successfully!")
