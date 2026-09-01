"""OCR engine abstraction (pluggable).

Resolved in order (first that imports cleanly wins):
  1. easyocr                -> deep-learning, best multilingual (English+Hindi)
  2. rapidocr-onnxruntime  -> lightweight ONNX engine, pure-pip

If none are available the pipeline falls back to a metadata-only path.
"""

from __future__ import annotations

import logging

log = logging.getLogger("doc_extractor.ocr")

_reader = None
_engine = None


def _load_reader():
    global _reader, _engine
    if _reader is not None:
        return _reader

    try:
        import easyocr
        _reader = easyocr.Reader(["en", "hi"], gpu=False)
        _engine = "easyocr"
        log.info("OCR engine loaded: EasyOCR (en+hi)")
        return _reader
    except Exception as exc:
        log.warning("EasyOCR unavailable (%s); trying RapidOCR.", exc)

    try:
        from rapidocr_onnxruntime import RapidOCR
        _reader = RapidOCR()
        _engine = "rapidocr"
        log.info("OCR engine loaded: RapidOCR (ONNX, legacy)")
        return _reader
    except Exception as exc:
        log.warning("RapidOCR (legacy) unavailable (%s). Trying rapidocr.", exc)

    try:
        from rapidocr import RapidOCR
        _reader = RapidOCR()
        _engine = "rapidocr"
        log.info("OCR engine loaded: RapidOCR (ONNX, v3)")
        return _reader
    except Exception as exc:
        log.warning("RapidOCR unavailable (%s). Using metadata-only path.", exc)
        _engine = "none"

    return _reader


def engine_name() -> str:
    if _engine is None:
        _load_reader()
    return _engine or "not-loaded"


def is_available() -> bool:
    try:
        _load_reader()
    except Exception:
        return False
    return _engine not in (None, "none")


def read_image(path: str) -> list[dict]:
    """Return a list of {box, text, conf} dicts for an image file."""
    _load_reader()
    if _engine == "none":
        return []
    try:
        return _run(path)
    except Exception as exc:
        log.warning("OCR read failed (%s): %s", path, exc)
        return []


def _run(path: str) -> list[dict]:
    if _engine == "easyocr":
        result = _reader.readtext(path)
        return [
            {
                "box": [list(map(float, pt)) for pt in item[0]],
                "text": item[1],
                "conf": float(item[2]),
            }
            for item in result
        ]

    result = _reader(path)

    if isinstance(result, tuple):
        result, _elapse = result
        out = []
        for item in result or []:
            try:
                box, text, score = item
            except ValueError:
                continue
            out.append({"box": box, "text": str(text), "conf": float(score)})
        return out

    if hasattr(result, "txts"):
        out = []
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            out.append(
                {
                    "box": box.tolist() if hasattr(box, "tolist") else box,
                    "text": str(text),
                    "conf": float(score),
                }
            )
        return out

    return []
