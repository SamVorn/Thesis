# src/anonymization/anonymization_pipeline.py
from src.anonymization.detector import PIIDetector
from src.anonymization.anonymizer import apply_strategy, STRATEGY_NONE


class AnonymizationPipeline:
    """
    Four Phases:
        1. detect() detect PII and apply scoring to every field
        2. review() print to the terminal for review
        3. confirm() accept or override each field anonymization through terminal 
        4. run() apply apply anonymization and store in new db
    """

    def __init__(self, source, detector: PIIDetector):
        self.source   = source
        self.detector = detector


    # detection
    def detect(self, survey_id: str = None) -> list:
        """
        Objectives:
        Load templates and responses 
        run full PII analysis 
        return PII fields
        should return a list of dicts sorted by value score:
            question_id, question_text, detected_labels, hit_count,
            total_responses, score, recommended_strategy, sample_hits
        """
        template = self.source.get_survey_template(survey_id)
        if template is None:
            print(f"No survey template found for survey_id={survey_id!r}")
            return []

        questions = template.get("questions", [])
        responses = list(self.source.iter_responses(survey_id))
        return self.detector.analyse_survey(questions, responses)

    # admin review
    def review(self, analysis: list) -> None:
        # print scores
        if not analysis:
            print("No fields to review.")
            return

        total = analysis[0]["total_responses"] if analysis else 0
        print("\n" + "-" * 70)
        print(f"  PII Report {total} response(s) analysed")
        print("-" * 70)

        for field in analysis:
            score  = field["score"]
            labels = field["detected_labels"] or ["—"]
            strat  = field["recommended_strategy"]
            hits   = field["hit_count"]

            badge = (
                "[HIGH  ]" if score >= 10 else
                "[MEDIUM]" if score >= 5  else
                "[LOW   ]" if score >= 2  else
                "[CLEAN ]"
            )

            print(f"\n  {badge}  Question : {field['question_id']!r}")
            if field["question_text"]:
                print(f"             Text     : {field['question_text']}")
            print(f"             Labels   : {', '.join(labels)}")
            print(f"             Hits     : {hits}/{field['total_responses']}  |  Score: {score}")
            # system recommended action to take on field
            print(f"             → Recommended: {strat.upper()}")

            if field["sample_hits"]:
                print("             Samples  :")
                for rid, val in field["sample_hits"]:
                    print(f"               • respondent {rid}: {val!r}")

        print("\n" + "=" * 70)

    # admin confirmation
    def confirm(self, analysis: list) -> list:
        """
        Objectives:
        ability to walk through each field
        Press Enter to accept the recommended strategy
        Type a name to override with: suppress | pseudonymize | generalize | none

        should return the analysis list with a 'chosen_strategy' key added to each field
        """
        VALID = {"suppress", "pseudonymize", "generalize", "none"}

        print("\n  STRATEGY CONFIRMATION")
        print("  Press Enter to accept a recommendation, or type an override.")
        print(f"  Valid options: {', '.join(sorted(VALID))}\n")

        confirmed = []
        for field in analysis:
            qid = field["question_id"]
            rec = field["recommended_strategy"]

            prompt = f"  [{qid}]  Score={field['score']}  Recommended={rec.upper()}  → Choice: "
            while True:
                raw = input(prompt).strip().lower()
                if raw == "":
                    chosen = rec
                    break
                if raw in VALID:
                    chosen = raw
                    break
                print(f"    Invalid. Choose from: {', '.join(sorted(VALID))}")

            entry = dict(field)
            entry["chosen_strategy"] = chosen
            confirmed.append(entry)
            print(f"    ✓ {qid}: {chosen.upper()}")

        print()
        return confirmed

    # running changes
    def run(self, survey_id: str = None, confirmed_analysis: list = None) -> list:
        """
        Objectives:
        should apply anonymization to every response
        """
        if confirmed_analysis is None:
            confirmed_analysis = self.detect(survey_id)

        # Build lookup: question_id → (strategy, detected_labels)
        strategy_map = {
            f["question_id"]: (
                f.get("chosen_strategy") or f["recommended_strategy"],
                f["detected_labels"],
            )
            for f in confirmed_analysis
        }

        anonymized_records = []
        audit_log          = []

        for resp in self.source.iter_responses(survey_id):
            rid          = resp.get("respondent_id", "unknown")
            answers      = resp.get("answers", {})
            anon_answers = {}

            for qid, raw_value in answers.items():
                strategy, labels = strategy_map.get(qid, (STRATEGY_NONE, []))
                anon_answers[qid] = apply_strategy(qid, raw_value, strategy, labels)

                if strategy != STRATEGY_NONE:
                    audit_log.append({
                        "respondent_id": rid,
                        "question_id":   qid,
                        "strategy":      strategy,
                    })

            anonymized_records.append({"respondent_id": rid, "answers": anon_answers})

        if audit_log and hasattr(self.source, "save_flags"):
            self.source.save_flags(survey_id, audit_log)

        print(f"  Done. {len(anonymized_records)} record(s) anonymized.")
        return anonymized_records