## Automated Exam Generation & Assessment Platform

### LIVE DEMO LINK - ch1-production-001.up.railway.app

## Problem Statement

Creating examinations from study material requires significant manual effort,
especially when educators need different difficulty levels or question formats.
This platform generates assessments directly from uploaded study material and
simplifies the evaluation process.

## Features

- Upload study material (PDF or text)
- Auto-detect chapters/topics from the content
- Generate question papers with adjustable difficulty (easy/medium/hard)
- Support multiple question types: MCQ and descriptive
- Auto-generate answer keys / model solutions
- Evaluate student responses and score them
- Show performance reports and feedback

## Tech Stack

- Backend: Python, Flask
- PDF parsing: pypdf
- AI: Google Gemini API for question generation, with a
  rule-based/template fallback generator when no API key is configured.
  Answer evaluation uses keyword-matching logic.
- Database: SQLite
- Frontend: HTML, Bootstrap

## Setup

- python -m venv venv
- venv\Scripts\activate
- pip install -r requirements.txt
- Set the `GEMINI_API_KEY` environment variable to enable live AI question
  generation (optional — without it, the app falls back to a topic-based
  template generator)
- python app.py
- Then open http://localhost:5000

## Team

- Aditi Sisodiya
- Anushka Vaishnav
