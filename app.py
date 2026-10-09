
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path

from flask import Flask, render_template, request
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_TEXT_CHARS = 12000
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_BYTES
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.logger.setLevel(logging.INFO)


def extract_pdf_text(pdf_path):
    try:
        reader = PdfReader(str(pdf_path))

        if reader.is_encrypted:
            raise ValueError(
                "This PDF is password-protected. Please upload an unlocked PDF."
            )

        parts = []
        total_chars = 0

        for page in reader.pages:
            page_text = page.extract_text() or ""

            if page_text.strip():
                parts.append(page_text)
                total_chars += len(page_text)

            if total_chars >= MAX_TEXT_CHARS:
                break

        text = "\n\n".join(parts).strip()

        if len(text) < 80:
            raise ValueError(
                "Not enough readable text found. If your PDF is scanned, "
                "please use a text-based PDF or OCR first."
            )

        return text[:MAX_TEXT_CHARS]

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "This PDF could not be opened. Please try another PDF."
        ) from exc


def extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)

        if not match:
            raise ValueError(
                "The AI returned an invalid response. Please try again."
            )

        return json.loads(match.group(0))


def validate_questions(payload, requested_count):
    raw_questions = (
        payload.get("questions", [])
        if isinstance(payload, dict)
        else payload
    )

    if not isinstance(raw_questions, list):
        raise ValueError("The AI did not return a valid question list.")

    questions = []

    for item in raw_questions:
        if not isinstance(item, dict):
            continue

        question_text = str(item.get("question", "")).strip()
        topic = str(item.get("topic", "General concepts")).strip()
        explanation = str(item.get("explanation", "")).strip()
        raw_options = item.get("options", [])

        if not question_text or not isinstance(raw_options, list):
            continue

        options = []

        for index, option in enumerate(raw_options[:4]):
            if isinstance(option, dict):
                value = str(
                    option.get("value", chr(65 + index))
                ).strip()
                label = str(
                    option.get("label", option.get("text", ""))
                ).strip()
            else:
                value = chr(65 + index)
                label = str(option).strip()

            if label:
                options.append({
                    "value": value,
                    "label": label
                })

        if len(options) != 4:
            continue

        answer = item.get("correctValues")

        if isinstance(answer, list):
            answer = answer[0] if answer else ""

        if not answer:
            answer = item.get(
                "correctAnswer",
                item.get("answer", "")
            )

        answer = str(answer).strip()

        valid_values = {option["value"] for option in options}
        label_lookup = {
            option["label"].casefold(): option["value"]
            for option in options
        }

        if answer not in valid_values:
            answer = label_lookup.get(answer.casefold(), "")

        if not answer:
            continue

        questions.append({
            "question": question_text,
            "topic": (topic or "General concepts")[:80],
            "options": options,
            "correctValues": [answer],
            "correctAnswer": answer,
            "explanation": explanation or
                "Review the relevant part of your study material."
        })

    if len(questions) < min(3, requested_count):
        raise ValueError(
            "The PDF did not contain enough material for a reliable quiz. "
            "Try a clearer or more detailed PDF."
        )

    return questions[:requested_count]


def generate_quiz(pdf_text, question_count, difficulty):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an educational quiz generator.

Create exactly {question_count} multiple-choice questions
from the study material provided below.

Difficulty: {difficulty}

Rules:
1. Use only information supported by the study material.
2. Avoid repeated questions.
3. Each question must have exactly four options.
4. Option values must be A, B, C and D.
5. Exactly one option must be correct.
6. Add a short topic label to every question.
7. Add a helpful explanation for each answer.
8. Match the selected difficulty.
9. Return valid JSON only. No Markdown.

Use this structure:
{{
  "questions": [
    {{
      "question": "Question text",
      "topic": "Topic label",
      "options": [
        {{"value": "A", "label": "Option A"}},
        {{"value": "B", "label": "Option B"}},
        {{"value": "C", "label": "Option C"}},
        {{"value": "D", "label": "Option D"}}
      ],
      "correctValues": ["A"],
      "explanation": "Short explanation"
    }}
  ]
}}

STUDY MATERIAL:
{pdf_text}
"""

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
    response_mime_type="application/json",
    temperature=0.25,
    max_output_tokens=3000
)
            )

            if not response or not response.text:
                raise RuntimeError("The AI returned an empty response.")

            payload = extract_json(response.text)

            return validate_questions(payload, question_count)

        except Exception as exc:
            message = str(exc).upper()

            temporary_error = any(code in message for code in (
                "503",
                "UNAVAILABLE",
                "429",
                "RESOURCE_EXHAUSTED",
                "TIMEOUT"
            ))

            if attempt == 0 and temporary_error:
                time.sleep(1)
                continue

            raise


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    pdf_path = None

    try:
        uploaded = (
            request.files.get("pdf_file")
            or request.files.get("file")
            or request.files.get("document")
        )

        if not uploaded or not uploaded.filename:
            return render_template(
                "index.html",
                error="Please choose a PDF first."
            ), 400

        if not uploaded.filename.lower().endswith(".pdf"):
            return render_template(
                "index.html",
                error="Only PDF files are supported."
            ), 400

        try:
            question_count = int(
                request.form.get("question_count", "10")
            )
        except (TypeError, ValueError):
            question_count = 10

        if question_count not in (5, 10, 15, 20):
            question_count = 10

        difficulty = request.form.get("difficulty", "Medium").title()

        if difficulty not in ("Easy", "Medium", "Hard"):
            difficulty = "Medium"

        safe_name = secure_filename(uploaded.filename)

        with tempfile.NamedTemporaryFile(
            prefix="quiz_",
            suffix=".pdf",
            dir=UPLOAD_FOLDER,
            delete=False
        ) as temp:
            pdf_path = Path(temp.name)

        uploaded.save(str(pdf_path))

        pdf_text = extract_pdf_text(pdf_path)

        questions = generate_quiz(
            pdf_text,
            question_count,
            difficulty
        )

        return render_template(
            "quiz.html",
            questions=questions,
            filename=safe_name,
            difficulty=difficulty
        )

    except ValueError as exc:
        return render_template(
            "index.html",
            error=str(exc)
        ), 400

    except Exception as exc:
        app.logger.exception("Quiz generation failed")

        message = str(exc).upper()

        if "GEMINI_API_KEY" in message:
            friendly_error = (
                "The website administrator needs to configure "
                "the Gemini API key."
            )
        elif "429" in message or "RESOURCE_EXHAUSTED" in message:
            friendly_error = (
                "The AI service is busy. Please wait a little and try again."
            )
        elif "503" in message or "UNAVAILABLE" in message:
            friendly_error = (
                "The AI service is temporarily unavailable. Try again shortly."
            )
        elif "404" in message and "MODEL" in message:
            friendly_error = (
                "The configured AI model is unavailable. "
                "The website administrator needs to check the model setting."
            )
        else:
            friendly_error = (
                "Quiz generation failed. Please try another text-based PDF."
            )

        return render_template(
            "index.html",
            error=friendly_error
        ), 500

    finally:
        if pdf_path:
            try:
                pdf_path.unlink(missing_ok=True)
            except OSError:
                app.logger.warning("Could not delete temporary PDF.")


@app.errorhandler(413)
def too_large(_error):
    return render_template(
        "index.html",
        error="PDF is larger than 15 MB. Please upload a smaller file."
    ), 413


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False
    )