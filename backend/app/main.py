"""FastAPI entry point. Run from backend/:  .venv\\Scripts\\uvicorn app.main:app --port 8000"""
import logging
import threading

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import emergency, llm, pricing, rag
from .config import BASE_DIR, get_settings
from .db import Base, engine, get_db
from .models import User
from .routers import auth, cases
from .security import current_user

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
Base.metadata.create_all(engine)

app = FastAPI(title="AI Healthcare Diagnosis & Medication Assistance", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


app.include_router(auth.router)
app.include_router(cases.router)


@app.on_event("startup")
def _startup():
    threading.Thread(target=rag.warm_up, daemon=True).start()


@app.get("/api/health")
def health():
    s = get_settings()
    return {"status": "ok", "llm": llm.active_provider(), "rag": rag.mode(), "ocr": bool(s.tesseract_cmd)}


@app.get("/api/emergency")
def emergency_guides():
    return {"guides": [g for g in emergency.guides() if g["id"] != "critical_lab"], "numbers": emergency.numbers()}


@app.get("/api/prices")
def prices(q: str, refresh: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return pricing.compare(db, q, refresh)


# Serve the built React app (frontend/dist) when present, so one server runs everything.
DIST = BASE_DIR.parent / "frontend" / "dist"


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    if not DIST.exists():
        return {"message": "API is running. Start the frontend with 'npm run dev' in frontend/."}
    target = (DIST / path).resolve()
    if path and target.is_file() and DIST.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(DIST / "index.html")
