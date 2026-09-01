"""FastAPI app exposing a browser UI for the document extraction system."""

from __future__ import annotations

import os
import time
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .core.excel_writer import generate_excel
from .core.pipeline import process_folder

ROOT = Path(__file__).resolve().parent.parent  # .../doc_extractor
DATA_DIR = ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
STATIC_DIR = ROOT / "backend" / "static"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Document Data Extraction System")


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


@app.post("/api/process")
def process():
    """Process whatever is currently inside data/input."""
    if not any(INPUT_DIR.iterdir()):
        return {"ok": False, "error": "No input folders found inside data/input."}

    start = time.time()
    rows = process_folder(str(INPUT_DIR))
    excel_path = _write_excel(rows, str(OUTPUT_DIR))
    elapsed = round(time.time() - start, 2)

    return {
        "ok": True,
        "rows": len(rows),
        "excel": Path(excel_path).name,
        "download_url": f"/api/download/{Path(excel_path).name}",
        "elapsed_seconds": elapsed,
    }


@app.post("/api/process-upload")
async def process_upload(file: UploadFile = File(...)):
    """Upload a ZIP of the main folder, extract it, then process."""
    if not file.filename.lower().endswith(".zip"):
        return {"ok": False, "error": "Please upload a .zip file."}

    run_id = str(int(time.time()))
    work_dir = DATA_DIR / "runs" / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / file.filename
    with open(zip_path, "wb") as fh:
        fh.write(await file.read())

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(work_dir)
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Invalid ZIP archive."}

    main_folder = _find_main_folder(work_dir)
    start = time.time()
    rows = process_folder(str(main_folder))
    excel_path = _write_excel(rows, str(OUTPUT_DIR))
    elapsed = round(time.time() - start, 2)

    return {
        "ok": True,
        "rows": len(rows),
        "excel": Path(excel_path).name,
        "download_url": f"/api/download/{Path(excel_path).name}",
        "elapsed_seconds": elapsed,
    }


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


def _list_input_folders():
    return [p.name for p in INPUT_DIR.iterdir() if p.is_dir()]


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
