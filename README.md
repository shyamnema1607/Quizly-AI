
# Quizly AI — AI Quiz Generator Website

Quizly AI is an AI-powered quiz generator website that creates quizzes from uploaded PDF documents using Google's Gemini API.

## Features

- Upload PDF documents
- Generate quizzes using AI
- Choose quiz difficulty
- Attempt multiple-choice questions
- View quiz score and performance
- Review correct answers and explanations
- Get topic-wise performance insights
- Responsive user interface

## Technologies Used

- Python
- Flask
- Google Gemini API
- HTML
- CSS
- JavaScript
- PyPDF

## Project Structure

```text
AI-Quiz-Generator-Website/
├── app.py
├── requirements.txt
├── Procfile
├── README.md
├── templates/
│   ├── index.html
│   └── quiz.html
└── static/
    └── style.css
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd AI-Quiz-Generator-Website
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure the Gemini API key

Get an API key from Google AI Studio.

On Windows PowerShell, run:

```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

Replace `YOUR_GEMINI_API_KEY` with your actual API key.

Never publish your API key on GitHub.

### 4. Run the application

```bash
python app.py
```

Open the local URL shown in your terminal, usually:

http://127.0.0.1:5000

## Deployment

The application can be deployed to a compatible hosting platform such as Render.

Configure the following environment variable in the hosting dashboard:

`GEMINI_API_KEY`

Use the following start command if required:

```bash
gunicorn app:app
```

Ensure the application binds to the host and port provided by the hosting platform.

## Security

- Keep API keys private.
- Store API keys in environment variables.
- Do not commit `.env` files containing secrets.

## License

This project is intended for educational and learning purposes.