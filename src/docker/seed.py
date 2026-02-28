"""
seed.py
Unified database seeder for survey anonymization

Uses Ollama (local LLM) to generate 100 realistic survey responses with naturally occurring PII
Why Ollama:
- Runs fully locally — no API keys, no cost, no data leaving your machine
- Critical for a PII tool: you don't want synthetic PII sent to external APIs
- Supports structured JSON output via prompt engineering
- Recommended models: llama3, mistral (install with `ollama pull llama3`)
"""

import argparse
import json
import re
import sys
import uuid
from typing import Optional

import requests

# db clients
def get_mongo_db(uri: str = "mongodb://localhost:27017", db_name: str = "thesis_pipeline"):
    try:
        from pymongo import MongoClient
        client = MongoClient(uri)
        return client[db_name]
    except ImportError:
        print("ERROR: pymongo not installed. Run: pip install pymongo")
        sys.exit(1)


def get_sql_engine(conn_str: str = "postgresql://thesis:thesis@localhost:5432/thesis_pipeline"):
    try:
        from sqlalchemy import create_engine
        return create_engine(conn_str)
    except ImportError:
        print("ERROR: sqlalchemy not installed. Run: pip install sqlalchemy psycopg2-binary")
        sys.exit(1)

# ollama llm client
def check_ollama(model: str, ollama_url: str) -> bool:
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        available = [m["name"].split(":")[0] for m in r.json().get("models", [])]
        if model not in available:
            print(f"ERROR: Model '{model}' not found in Ollama.")
            print(f"       Available: {available or 'none'}")
            print(f"       Install it with: ollama pull {model}")
            return False
        return True
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to Ollama. Is it running?")
        print("       Start it with: ollama serve")
        return False

def generate_responses_batch(
    questions: list[dict],
    count: int,
    model: str,
    ollama_url: str,
    batch_size: int = 10,
) -> list[dict]:
    question_lines = "\n".join(
        '  "' + q["question_id"] + '": "<answer to: ' + q["text"] + '>"'
        for q in questions
    )
    example_key = questions[0]["question_id"]

    all_responses = []
    batches = [
        min(batch_size, count - i)
        for i in range(0, count, batch_size)
    ]

    print(f"\nGenerating {count} responses via Ollama ({model}) in {len(batches)} batches...")

    for batch_num, batch_count in enumerate(batches, start=1):
        print(f"  Batch {batch_num}/{len(batches)} ({batch_count} responses)...", end=" ", flush=True)

        # Build prompt without .format() to avoid conflicts with JSON curly braces
        prompt = (
            "You are generating realistic fake survey responses for software testing.\n"
            f"Generate {batch_count} different people's responses as a JSON array.\n"
            "Include realistic PII where appropriate (names, emails, phone numbers, addresses, dates).\n"
            "Vary the responses — different demographics, formats, edge cases.\n\n"
            "Questions:\n"
            f"{question_lines}\n\n"
            f"Respond ONLY with a valid JSON array of {batch_count} objects. Each object maps question_id to answer string.\n"
            "Example format:\n"
            "[\n"
            f'  {{"{example_key}": "Some Answer", ...}},\n'
            "  ...\n"
            "]\n"
            "No explanation. No markdown. Pure JSON array only."
        )


        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.9}
        }

        try:
            r = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=120)
            r.raise_for_status()
            raw = r.json()["response"].strip()

            # Strip markdown fences if model adds them anyway
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"^```\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

            parsed = json.loads(raw)

            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array")

            all_responses.extend(parsed[:batch_count])
            print(f"OK ({len(parsed)} received)")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"PARSE ERROR: {e}")
            print(f"  Raw response snippet: {raw[:200]}")
            print("  Filling batch with empty responses as fallback.")
            for _ in range(batch_count):
                all_responses.append({q["question_id"]: "" for q in questions})

        except requests.exceptions.Timeout:
            print("TIMEOUT — model took too long. Try a smaller model or reduce batch size.")
            sys.exit(1)

    return all_responses[:count]


# question input
def prompt_for_questions() -> list[dict]:
    print("\n Define Survey Questions")
    print("Enter each question on a new line.")
    print("Press ENTER twice (blank line) when done.\n")

    questions = []
    q_num = 1

    while True:
        text = input(f"Q{q_num}: ").strip()
        if not text:
            if not questions:
                print("You must enter at least one question.")
                continue
            break
        questions.append({
            "question_id": f"q{q_num}",
            "text": text
        })
        q_num += 1

    print(f"\n{len(questions)} question(s) recorded.")
    return questions


# database seeding 
def seed_mongo(
    survey_id: str,
    questions: list[dict],
    responses: list[dict],
    reset: bool,
):
    print("\nSeeding MongoDB")
    db = get_mongo_db()

    if reset:
        db.drop_collection("surveys")
        db.drop_collection("responses")
        print("  Collections dropped.")

    db["surveys"].insert_one({
        "survey_id": survey_id,
        "questions": questions
    })

    docs = [
        {
            "survey_id": survey_id,
            "respondent_id": str(uuid.uuid4()),
            "answers": r
        }
        for r in responses
    ]
    db["responses"].insert_many(docs)
    print(f"  Inserted 1 survey template + {len(docs)} responses into MongoDB.")


def seed_sql(
    survey_id: str,
    questions: list[dict],
    responses: list[dict],
    reset: bool,
):
    print("\nSeeding Postgres")
    from sqlalchemy import text as sql_text

    engine = get_sql_engine()
    template = {"survey_id": survey_id, "questions": questions}

    with engine.begin() as conn:
        if reset:
            conn.execute(sql_text("DELETE FROM pii_flags"))
            conn.execute(sql_text("DELETE FROM survey_responses"))
            conn.execute(sql_text("DELETE FROM survey_templates"))
            print("  Tables cleared.")

        conn.execute(
            sql_text("INSERT INTO survey_templates (survey_id, template_json) VALUES (:id, :data)"),
            {"id": survey_id, "data": json.dumps(template)}
        )

        for r in responses:
            respondent_id = str(uuid.uuid4())
            conn.execute(
                sql_text(
                    "INSERT INTO survey_responses (respondent_id, survey_id, answers_json) "
                    "VALUES (:r, :s, :a)"
                ),
                {"r": respondent_id, "s": survey_id, "a": json.dumps(r)}
            )

    print(f"  Inserted 1 survey template + {len(responses)} responses into Postgres.")


# CLI
def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed survey databases with LLM-generated responses."
    )
    parser.add_argument(
        "--db",
        choices=["mongo", "sql", "both"],
        required=True,
        help="Which database(s) to seed."
    )
    parser.add_argument(
        "--survey-id",
        default="survey1",
        help="Survey ID to use (default: survey1)."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="Number of responses to generate (default: 100)."
    )
    parser.add_argument(
        "--model",
        default="llama3",
        help="Ollama model to use (default: llama3)."
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434)."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear existing data before seeding."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print("  Survey Pipeline Seeder  —  Powered by Ollama")

    # check Ollama
    if not check_ollama(args.model, args.ollama_url):
        sys.exit(1)

    # get questions from user
    questions = prompt_for_questions()

    # confirm before generating
    print(f"\nAbout to generate {args.count} responses for survey '{args.survey_id}'")
    print(f"Target: {args.db.upper()}  |  Model: {args.model}")
    confirm = input("Proceed? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # generate via Ollama
    responses = generate_responses_batch(
        questions=questions,
        count=args.count,
        model=args.model,
        ollama_url=args.ollama_url,
    )

    # seed target DB(s)
    if args.db in ("mongo", "both"):
        seed_mongo(args.survey_id, questions, responses, args.reset)

    if args.db in ("sql", "both"):
        seed_sql(args.survey_id, questions, responses, args.reset)

    print("\n✓ Seeding complete.")
    print(f"  Survey ID : {args.survey_id}")
    print(f"  Responses : {len(responses)}")
    print(f"  Questions : {len(questions)}")


if __name__ == "__main__":
    main()