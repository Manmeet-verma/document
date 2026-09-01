# Automated Document Data Extraction & Excel Management System

A Python web application that automatically scans folders of Aadhaar & RC (vehicle
registration certificate) images, extracts the information using OCR, matches
front/back scans of each document, and generates a clean, formatted Excel file.

---

## Features

- **Automatic folder scanning** — scans a main folder of person subfolders.
- **Document detection & pairing** — identifies and matches Aadhaar front/back
  and RC front/back images inside each person's subfolder.
- **OCR extraction** — extracts Name, Aadhaar Number, DOB, Gender, Father's name,
  Vehicle Registration Number, Owner Name, Chassis Number, Engine Number,
  Registration Date, Insurance / Fitness / Tax validity, and more.
- **Honest data handling** — any field that cannot be read confidently is marked
  **`Not Detected`** or **`Verification Required`** (never guessed).
- **Formatted Excel output** — one row per person, color-coded cells, frozen
  header, auto-filter, alternating rows, and **clickable hyperlinks to the
  original images** for manual verification.
- **Browser UI** — upload a ZIP or scan a local folder, then download the Excel.

---

## Tech stack

| Layer      | Technology                                              |
|------------|---------------------------------------------------------|
| Backend    | Python 3.10+, **FastAPI** + Uvicorn                    |
| OCR        | **EasyOCR** (en+hi) → falls back to **RapidOCR** (ONNX) |
| Excel      | **openpyxl** (styling, hyperlinks, filters)            |
| Frontend   | Plain HTML/CSS/JS served by FastAPI                     |

---

## Folder structure expected

```
Main_Folder/
├── Person_001/
│   ├── aadhaar_front.jpg
│   ├── aadhaar_back.jpg
│   ├── rc_front.jpg
│   └── rc_back.jpg
├── Person_002/
│   └── ...
└── ...
```

---

## Installation

```bash
cd doc_extractor
pip install -r requirements.txt
```

## Usage

### Web UI

```bash
python3 run.py          # http://127.0.0.1:8000
python3 run.py --port 9000
```

### CLI (standalone)

```bash
python3 extract.py                          # auto-scan system folders + data/input
python3 extract.py /path/to/Main_Folder     # scan specific folder
python3 extract.py -v                       # verbose output
python3 extract.py -o custom.xlsx           # custom output path
```

---

## Excel output columns

Folder/Person ID, Aadhaar Images (links), RC Images (links),
Name, Aadhaar Number, DOB, Gender, Father/Spouse Name,
Vehicle Registration Number, Vehicle Owner Name, Chassis Number,
Engine Number, Make/Model, Registration Date, Insurance Valid Upto,
Fitness Valid Upto, Tax Valid Upto

Green = detected | Yellow = Verification Required / Not Detected

---

## Project layout

```
doc_extractor/
├── run.py                     # web server launcher
├── extract.py                 # standalone CLI runner
├── requirements.txt
├── README.md
├── backend/
│   ├── app.py                 # FastAPI routes
│   ├── static/index.html      # browser UI
│   └── core/
│       ├── ocr_engine.py      # OCR (EasyOCR → RapidOCR)
│       ├── document_classifier.py  # Aadhaar/RC front/back detection
│       ├── extractor.py       # regex field extraction
│       ├── excel_writer.py    # formatted Excel + hyperlinks
│       └── pipeline.py        # scan → OCR → classify → extract
└── data/
    ├── input/                 # drop person folders here
    ├── output/                # generated Excel files
    └── uploads/               # temp ZIP uploads
```
