from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_db
from backend.routers import batch, documents, findings, presidio, projects, rules
from backend.services.batch import recover_interrupted_jobs

init_db()
recover_interrupted_jobs()

app = FastAPI(title="aud_it", description="Local-first PDF redaction")

app.include_router(documents.router)
app.include_router(projects.router)
app.include_router(findings.router)
app.include_router(rules.router)
app.include_router(batch.router)
app.include_router(presidio.router)

frontend_dir = settings.frontend_dir


@app.get("/")
def index():
    index_path = frontend_dir / "index.html"
    return FileResponse(index_path)


app.mount("/css", StaticFiles(directory=frontend_dir / "css"), name="css")
app.mount("/js", StaticFiles(directory=frontend_dir / "js"), name="js")
