# HealthAssist AI

**AI-powered healthcare diagnosis and medication assistance system.**

A web app where a patient enters their details and symptoms, answers follow-up questions written by an AI,
and uploads lab reports. The app then gives them:

- possible conditions, each with a confidence level and its reasoning
- a risk level, from low to emergency
- medicine information for a doctor to review, checked against allergies and interactions, with a daily timetable
- a 7-day diet chart, either with medicines or as a natural no-medicine plan for mild cases
- live medicine price comparison across online pharmacies
- emergency first-aid guidance
- a downloadable PDF report

> ⚠️ This is a decision-support and learning project. It does **not** diagnose or prescribe.
> Always consult a qualified doctor. In an emergency in India call **112** or **108**.

👉 **New here? Follow [SETUP_GUIDE.md](SETUP_GUIDE.md)** for step-by-step download, install, API key and usage instructions.

---

## Features

| Feature | What it does |
|---|---|
| Patient profile | Age, sex, conditions, allergies, current medicines, diet type, meal times, emergency contact (stored encrypted) |
| Smart follow-up questions | The AI asks 1–3 questions at a time until it has enough information, and says if a lab test is needed |
| Lab report reading | Upload a PDF or photo. Text is read with OCR, and values such as Hb, platelets and TSH are flagged normal, low, high or critical |
| Medical knowledge (RAG) | Answers are grounded in a vector database of curated medical knowledge, and sources are cited |
| Multi-agent analysis | 7 agents: Symptom, Report, Knowledge, Orchestrator, Risk, Medication, Diet (LangGraph) |
| Medicine safety | Medicines come only from a curated list and are checked against allergies (typos are caught too), conditions and drug interactions |
| Medicine timetable | Doses are placed at the right times: before or after food, bedtime, at least 6 hours apart |
| 7-day diet chart | Indian veg or non-veg meals that respect allergies, with a *natural (no medicine)* version for mild cases |
| Price comparison | Live prices from PharmEasy, Netmeds, Tata 1mg and Apollo Pharmacy, compared per tablet so different pack sizes are fair |
| Emergency detection | Danger signs (chest pain, stroke signs, critical lab values…) instantly show first-aid steps and 112/108 call buttons |
| PDF report | One structured report with every section |
| Security | bcrypt passwords, login tokens that expire, login lockout, encrypted database fields and files, audit log, account deletion |

## How it works

```
Profile → Symptoms → AI follow-up questions → Lab report upload (if needed) → OCR + lab flags
   → Symptom agent → Report agent → Knowledge agent (RAG) → Orchestrator → Risk agent
        → emergency?  yes → emergency guidance
                      no  → Medication agent → Diet agent → Final report + PDF + price comparison
```

Safety-critical steps are plain code, not AI: emergency detection, lab flags, the risk level, medicine choice and checks, and diet filtering.
The AI writes the questions, the summaries and the reasoning, and every AI answer is checked against a Pydantic schema before it is used.
If no AI key is set, a built-in rule engine takes over, so the app always works.

## Tech stack

**Backend:** Python, FastAPI, SQLAlchemy (SQLite or PostgreSQL), Pydantic, LangGraph, ChromaDB, Gemini / Groq, PyMuPDF, Tesseract OCR, ReportLab, bcrypt, JWT, Fernet encryption
**Frontend:** React 18, Vite

## Quick start (Windows)

```
setup.bat     (first time only: installs everything)
start.bat     (runs the app at http://127.0.0.1:8000)
```

Put your free Gemini API key in `backend\.env` (see [SETUP_GUIDE.md](SETUP_GUIDE.md#4-add-your-ai-api-key)).

## Project structure

```
backend/
  app/              API and logic: agents, triage, labs (OCR), rag, medication, diet, pricing, pdf_report, security
  data/             curated knowledge: conditions, medicines, lab ranges, foods, remedies, emergency guides
  knowledge_base/   optional extra documents for the AI to search
  demo/             sample lab report PDF for trying the upload
  scripts/          make_demo.py (creates a demo patient), import_prices.py
  tests/            automated tests
  .env.example      settings template (copy to .env and add your key)
frontend/           React website
setup.bat / start.bat / dev.bat
```

## Tests

```
cd backend
.venv\Scripts\python -m pytest tests -q
```

## License

For educational use.
