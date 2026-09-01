"""FastAPI app exposing a browser UI for the document extraction system."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .core.excel_writer import generate_excel
from .core.pipeline import discover_persons, process_folder

log = logging.getLogger("doc_extractor.app")

ROOT = Path(__file__).resolve().parent.parent  # .../doc_extractor
DATA_DIR = Path(os.environ.get("DATA_ROOT", ROOT / "data"))
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
STATIC_DIR = ROOT / "backend" / "static"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
INPUT_DIR.mkdir(parents=True, exist_ok=True)

# Starlette spools large uploads to tempfile.tempdir; force it onto the
# disk-backed data dir instead of RAM-backed /tmp so big zips don't blow
# up memory or fill tmpfs (which would kill the upload with "Failed to fetch").
SPOOL_DIR = DATA_DIR / "spool"
SPOOL_DIR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SPOOL_DIR)

app = FastAPI(title="Document Data Extraction System")

# Simple in-memory background job registry.
JOBS: dict[str, dict] = {}
_worker_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="extract")


def _new_job(job_id: str, source: str) -> dict:
    job = {
        "id": job_id,
        "source": source,
        "status": "queued",  # queued | running | done | error
        "message": "Queued...",
        "rows": 0,
        "excel": "",
        "download_url": "",
        "imported_to_input": [],
        "elapsed_seconds": 0.0,
        "error": "",
    }
    JOBS[job_id] = job
    return job


def _run_job(job_id: str, main_folder: Path):
    job = JOBS[job_id]
    start = time.time()
    try:
        job["status"] = "running"

        def progress(i: int, total: int, person_id: str, phase: str):
            job["message"] = f"({i}/{total}) {person_id}: {phase}"

        rows = process_folder(str(main_folder), progress=progress)
        excel_path = _write_excel(rows, str(OUTPUT_DIR))
        imported = _import_to_input(main_folder)

        job.update(
            status="done",
            message=f"Processed {len(rows)} person(s).",
            rows=len(rows),
            excel=Path(excel_path).name,
            download_url=f"/api/download/{Path(excel_path).name}",
            imported_to_input=imported,
            elapsed_seconds=round(time.time() - start, 2),
        )
    except Exception as exc:
        log.exception("Job %s failed", job_id)
        job.update(status="error", message="Processing failed.", error=str(exc))


def _start_job(job_id: str, main_folder: Path) -> dict:
    _new_job(job_id, str(main_folder))
    _worker_pool.submit(_run_job, job_id, main_folder)
    return JOBS[job_id]


@app.get("/", response_class=HTMLResponse)
def index():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return html


@app.get("/api/status")
def status():
    from .core import ocr_engine

    return {
        "ocr_engine": ocr_engine.engine_name(),
        "ocr_available": ocr_engine.is_available(),
        "data_dir": str(INPUT_DIR),
        "output_dir": str(OUTPUT_DIR),
        "input_folders": _list_input_folders(),
    }


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return {"ok": False, "error": "Job not found."}
    return {"ok": True, "job": job}


@app.post("/api/process")
def process():
    """Start a background job processing whatever is inside data/input."""
    try:
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": f"Cannot create data/input: {exc}"}

    try:
        has_input = any(INPUT_DIR.iterdir())
    except OSError as exc:
        return {"ok": False, "error": f"Cannot read data/input: {exc}"}

    if not has_input:
        return {"ok": False, "error": "No input folders found inside data/input."}

    job = _start_job(f"folder_{int(time.time() * 1000)}", INPUT_DIR)
    return {"ok": True, "job_id": job["id"], "status": job["status"]}


@app.post("/api/process-upload")
async def process_upload(file: UploadFile = File(...)):
    """Upload a ZIP of the main folder, extract it, then process in background."""
    if not file.filename.lower().endswith(".zip"):
        return {"ok": False, "error": "Please upload a .zip file."}

    run_id = str(int(time.time() * 1000))
    work_dir = DATA_DIR / "runs" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / file.filename

    # Stream to disk in chunks instead of buffering the whole zip in memory.
    try:
        with open(zip_path, "wb") as fh:
            shutil.copyfileobj(file.file, fh, length=1024 * 1024)
    except OSError as exc:
        return {"ok": False, "error": f"Could not save upload: {exc}"}

    with open(zip_path, "rb") as fh:
        head = fh.read(4)
    if head != b"PK\x03\x04":
        return {"ok": False, "error": "Invalid ZIP archive (bad header)."}

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work_dir)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Invalid ZIP archive."}

    main_folder = _find_main_folder(work_dir)
    job = _start_job(run_id, main_folder)
    return {"ok": True, "job_id": job["id"], "status": job["status"]}


@app.get("/api/download/{filename}")
def download(filename: str):
    target = OUTPUT_DIR / os.path.basename(filename)
    if not target.exists():
        return {"ok": False, "error": "File not found."}
    return FileResponse(
        target,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=target.name,
    )


def _write_excel(rows: list[dict], output_dir: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"extracted_data_{ts}.xlsx")
    return generate_excel(rows, out_path)


def _find_main_folder(work_dir: Path) -> Path:
    zip_name = ""
    for p in work_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".zip":
            zip_name = p.name
    entries = [p for p in work_dir.iterdir() if p.name != zip_name]
    dirs = [p for p in work_dir.iterdir() if p.is_dir()]
    if len(dirs) == 1 and len(entries) == 1:
        return dirs[0]
    return work_dir


def _import_to_input(main_folder: Path) -> list[str]:
    """Copy every discovered person folder into data/input so the upload can
    also be processed later via the 'Scan & Process data/input' option."""
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    for person_dir in discover_persons(str(main_folder)):
        name = os.path.basename(person_dir)
        dest = INPUT_DIR / name
        if dest.exists():
            i = 1
            while (INPUT_DIR / f"{name}_{i}").exists():
                i += 1
            dest = INPUT_DIR / f"{name}_{i}"
        shutil.copytree(person_dir, dest, dirs_exist_ok=True)
        imported.append(dest.name)
    return imported


def _list_input_folders():
    try:
        return [p.name for p in INPUT_DIR.iterdir() if p.is_dir()]
    except OSError:
        return []


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
