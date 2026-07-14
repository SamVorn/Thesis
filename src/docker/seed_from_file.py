

import argparse
import json
import re
import sys
import uuid
from pathlib import Path

import requests


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


def load_questions(path: str) -> tuple[str, list[dict]]:
   
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Questions file not found: {path}")
        sys.exit(1)

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse JSON from {path}: {e}")
        sys.exit(1)

    # Layout A — dict with "questions" key
    if isinstance(data, dict) and "questions" in data:
        survey_id = data.get("survey_id", p.stem)
        questions = data["questions"]

    # Layout B — top-level list
    elif isinstance(data, list):
        survey_id = p.stem
        questions = data

    else:
        print(f"ERROR: Unrecognised format in {path}.")
        print("       Expected a dict with a 'questions' key, or a top-level list.")
        sys.exit(1)

    # Normalise: ensure question_id and text fields exist
    normalised = []
    for i, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            print(f"  WARNING: Skipping non-dict entry at index {i}: {q!r}")
            continue

        qid  = q.get("question_id") or q.get("id") or f"q{i}"
        text = q.get("text") or q.get("question_text") or q.get("question") or ""

        if not text:
            print(f"  WARNING: Question {qid} has no text — skipping.")
            continue

        normalised.append({"question_id": str(qid), "text": text})

    if not normalised:
        print("ERROR: No valid questions found in the file.")
        sys.exit(1)

    return survey_id, normalised


def check_ollama(model: str, ollama_url: str) -> bool:
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=5)
        r.raise_for_status()
        available = [m["name"].split(":")[0] for m in r.json().get("models", [])]
        # Also check full tag match (e.g. "llama3.1:8b")
        available_full = [m["name"] for m in r.json().get("models", [])]
        if model not in available and model not in available_full:
            print(f"ERROR: Model '{model}' not found in Ollama.")
            print(f"       Available: {available_full or 'none'}")
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
    batches = [min(batch_size, count - i) for i in range(0, count, batch_size)]

    print(f"\n  Generating {count} responses via Ollama ({model}) in {len(batches)} batch(es)...")

    for batch_num, batch_count in enumerate(batches, start=1):
        print(f"  Batch {batch_num}/{len(batches)} ({batch_count} responses)...", end=" ", flush=True)

        prompt = (
            "You are generating realistic fake survey responses for software testing.\n"
            f"Generate {batch_count} different people's responses as a JSON array.\n"
            "Include realistic PII where appropriate (names, emails, phone numbers, addresses, dates).\n"
            "Vary the responses — different demographics, formats, edge cases.\n\n"
            "Questions:\n"
            f"{question_lines}\n\n"
            f"Respond ONLY with a valid JSON array of {batch_count} objects. "
            "Each object maps question_id to answer string.\n"
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
            "options": {"temperature": 0.9},
        }

        raw = ""
        try:
            r = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=180)
            r.raise_for_status()
            raw = r.json()["response"].strip()

            # Strip markdown fences if the model adds them
            raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"^```\s*",     "", raw, flags=re.MULTILINE)
            raw = re.sub(r"\s*```$",     "", raw)

            # Extract the outermost JSON array in case of extra prose
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                raw = match.group(0)

            parsed = json.loads(raw)

            if not isinstance(parsed, list):
                raise ValueError("Expected a JSON array")

            all_responses.extend(parsed[:batch_count])
            print(f"OK ({len(parsed)} received)")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"PARSE ERROR: {e}")
            if raw:
                print(f"  Raw response snippet: {raw[:300]}")
            print("  Filling batch with empty responses as fallback.")
            for _ in range(batch_count):
                all_responses.append({q["question_id"]: "" for q in questions})

        except requests.exceptions.Timeout:
            print("TIMEOUT — model took too long.")
            print("  Try: --batch-size 5  or  --model mistral:7b")
            sys.exit(1)

        except requests.exceptions.RequestException as e:
            print(f"REQUEST ERROR: {e}")
            sys.exit(1)

    return all_responses[:count]


def seed_mongo(
    survey_id: str,
    questions: list[dict],
    responses: list[dict],
    reset: bool,
    mongo_uri: str,
    mongo_db: str,
):
    print("\n  Seeding MongoDB...")
    db = get_mongo_db(uri=mongo_uri, db_name=mongo_db)

    if reset:
        db.drop_collection("surveys")
        db.drop_collection("responses")
        db.drop_collection("flags")
        db.drop_collection("responses_anonymized")
        print("  Collections dropped.")

    db["surveys"].insert_one({
        "survey_id": survey_id,
        "questions": questions,
    })

    docs = [
        {
            "survey_id":     survey_id,
            "respondent_id": str(uuid.uuid4()),
            "answers":       r,
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
    sql_conn: str,
):
    print("\n  Seeding Postgres...")
    from sqlalchemy import text as sa_text

    engine = get_sql_engine(sql_conn)
    template = {"survey_id": survey_id, "questions": questions}

    with engine.begin() as conn:
        if reset:
            conn.execute(sa_text("DELETE FROM pii_flags"))
            conn.execute(sa_text("DELETE FROM survey_responses"))
            conn.execute(sa_text("DELETE FROM survey_templates"))
            print("  Tables cleared.")

        conn.execute(
            sa_text("INSERT INTO survey_templates (survey_id, template_json) VALUES (:id, :data)"),
            {"id": survey_id, "data": json.dumps(template)},
        )

        for r in responses:
            conn.execute(
                sa_text(
                    "INSERT INTO survey_responses (respondent_id, survey_id, answers_json) "
                    "VALUES (:r, :s, :a)"
                ),
                {"r": str(uuid.uuid4()), "s": survey_id, "a": json.dumps(r)},
            )

    print(f"  Inserted 1 survey template + {len(responses)} responses into Postgres.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Seed survey DB from a questions JSON file (no interactive input).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python seed_from_file.py --questions questions.json --db mongo
  python seed_from_file.py --questions questions.json --db mongo --survey-id exp_300 --count 50
  python seed_from_file.py --questions questions.json --db both --reset --no-confirm
  python seed_from_file.py --questions questions.json --db mongo --model mistral:7b --batch-size 5
        """,
    )

    parser.add_argument(
        "--questions", required=True,
        help="Path to JSON file containing survey questions.",
    )
    parser.add_argument(
        "--db", choices=["mongo", "sql", "both"], required=True,
        help="Which database(s) to seed.",
    )
    parser.add_argument(
        "--survey-id", default=None,
        help="Override survey ID (default: taken from file, or filename stem).",
    )
    parser.add_argument(
        "--count", type=int, default=50,
        help="Number of responses to generate per survey (default: 50).",
    )
    parser.add_argument(
        "--model", default="llama3.1:8b",
        help="Ollama model to use (default: llama3.1:8b).",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Responses per Ollama batch (default: 10). Reduce if you get timeouts.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Drop/clear existing data before seeding.",
    )
    parser.add_argument(
        "--no-confirm", action="store_true",
        help="Skip the confirmation prompt (useful for scripting).",
    )
    parser.add_argument(
        "--mongo-uri", default="mongodb://localhost:27017",
        help="MongoDB connection URI (default: mongodb://localhost:27017).",
    )
    parser.add_argument(
        "--mongo-db", default="thesis_pipeline",
        help="MongoDB database name (default: thesis_pipeline).",
    )
    parser.add_argument(
        "--sql-conn",
        default="postgresql://thesis:thesis@localhost:5432/thesis_pipeline",
        help="SQLAlchemy connection string for Postgres.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    print("\n  Survey Pipeline Seeder (File Mode)")
    print("  ====================================")

    # Load questions from file
    file_survey_id, questions = load_questions(args.questions)

    # CLI --survey-id overrides what's in the file
    survey_id = args.survey_id or file_survey_id

    print(f"\n  Questions file : {args.questions}")
    print(f"  Questions      : {len(questions)}")
    print(f"  Survey ID      : {survey_id}")
    print(f"  Target DB      : {args.db.upper()}")
    print(f"  Responses      : {args.count}")
    print(f"  Model          : {args.model}")
    print(f"  Batch size     : {args.batch_size}")
    print(f"  Reset          : {args.reset}")

    # Check Ollama is reachable
    if not check_ollama(args.model, args.ollama_url):
        sys.exit(1)

    # Confirm before generating (skippable)
    if not args.no_confirm:
        confirm = input("\n  Proceed? [y/N]: ").strip().lower()
        if confirm != "y":
            print("  Aborted.")
            sys.exit(0)

    # Generate responses via Ollama
    responses = generate_responses_batch(
        questions=questions,
        count=args.count,
        model=args.model,
        ollama_url=args.ollama_url,
        batch_size=args.batch_size,
    )

    # Seed target DB(s)
    if args.db in ("mongo", "both"):
        seed_mongo(
            survey_id=survey_id,
            questions=questions,
            responses=responses,
            reset=args.reset,
            mongo_uri=args.mongo_uri,
            mongo_db=args.mongo_db,
        )

    if args.db in ("sql", "both"):
        seed_sql(
            survey_id=survey_id,
            questions=questions,
            responses=responses,
            reset=args.reset,
            sql_conn=args.sql_conn,
        )

    print("\n  Seeding complete.")
    print(f"  Survey ID  : {survey_id}")
    print(f"  Questions  : {len(questions)}")
    print(f"  Responses  : {len(responses)}")


if __name__ == "__main__":
    main()