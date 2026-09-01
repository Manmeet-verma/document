"""Document type detection and front/back matching.

Images inside a person's subfolder are classified as one of:
  AADHAAR_FRONT, AADHAAR_BACK, RC_FRONT, RC_BACK

Classification uses keywords found in the OCR text and falls back to the
filename for convenience. Pairing is done per-document type.
"""

from __future__ import annotations

import os
import re

AADHAAR_FRONT_TOKENS = [
    "aadhaar", "aadhar", "govt of india", "government of india",
    "unique identification", "enrolment", "enrollment number",
    "to download", "vid", "virtual id", "y our aadhaar", "birth", "gender",
]

AADHAAR_BACK_TOKENS = [
    "address", "pin", "postal", "district", "state", "changed address",
    "permanent address", "shifting", "update", "qr code", "aadhaar no",
    "aadhaar number",
]

RC_FRONT_TOKENS = [
    "registration", "registering authority", "office", "rc no", "regd.",
    "registered owner", "maker", "chassis", "engine", "fuel", "class",
    "categories of vehicles", "mv tax", "tax upto", "colour", "model",
    "unladen", "r.c.", "rc details",
]

RC_BACK_TOKENS = [
    "hypothecation", "insurance", "policy", "valid upto",
    "vehicle inspection", "fitness", "permit", "national permit",
    "ncb", "comments", "in case of transfer", "bank", "lender", "financier",
]

AADHAAR_RX = re.compile(r"\b(?:aadhaar|aadhar)\b", re.IGNORECASE)
RC_RX = re.compile(r"\b(?:rc|registration certificate|r\.c\.)\b", re.IGNORECASE)

SIDE_ONLY_FRONT = ["y our aadhaar", "enrolment", "enrollment", "birth"]
SIDE_ONLY_BACK = ["changed address", "permanent address", "shifting", "qr code"]


def _score(text: str, tokens: list[str]) -> float:
    lowered = text.lower()
    hits = sum(1 for t in tokens if t.lower() in lowered)
    return hits / max(1, len(tokens))


def _side_from_text(text: str, tokens_front: list[str], tokens_back: list[str]) -> str | None:
    s_front = _score(text, tokens_front)
    s_back = _score(text, tokens_back)
    if s_front > s_back + 0.05:
        return "front"
    if s_back > s_front + 0.05:
        return "back"
    return None


def classify(image_path: str, ocr_text: str) -> tuple[str, float]:
    """Return (doc_type, confidence) where doc_type is one of the four kinds."""
    lower_text = ocr_text.lower()
    fname = os.path.basename(image_path).lower()

    doc = "unknown"
    side = None
    conf = 0.0

    # Doc type by content
    if AADHAAR_RX.search(lower_text):
        doc = "aadhaar"
    elif RC_RX.search(lower_text):
        doc = "rc"
    else:
        s_rc = _score(lower_text, RC_FRONT_TOKENS) + _score(lower_text, RC_BACK_TOKENS)
        s_ad = _score(lower_text, AADHAAR_FRONT_TOKENS) + _score(lower_text, AADHAAR_BACK_TOKENS)
        if s_rc > s_ad:
            doc = "rc"
        elif s_ad > s_rc:
            doc = "aadhaar"

    # Side by content
    if doc == "aadhaar":
        for t in SIDE_ONLY_FRONT:
            if t in lower_text:
                side, conf = "front", 0.95
                break
        if side is None:
            for t in SIDE_ONLY_BACK:
                if t in lower_text:
                    side, conf = "back", 0.95
                    break
        if side is None:
            side = _side_from_text(lower_text, AADHAAR_FRONT_TOKENS, AADHAAR_BACK_TOKENS)
    elif doc == "rc":
        for t in SIDE_ONLY_FRONT:
            if t in lower_text:
                side, conf = "front", 0.95
                break
        if side is None:
            side = _side_from_text(lower_text, RC_FRONT_TOKENS, RC_BACK_TOKENS)

    # Fallback to filename
    if side is None:
        if re.search(r"(aadhaar|aadhar)", fname):
            doc = "aadhaar"
        elif re.search(r"\brc\b|registration", fname):
            doc = "rc"
        if re.search(r"(back|reverse|rear|dorso)", fname):
            side, conf = "back", conf if conf else 0.6
        elif re.search(r"(front|obverse|face|top)", fname):
            side, conf = "front", conf if conf else 0.6
        else:
            side = "front" if doc == "aadhaar" else None

    if doc == "unknown":
        return "unknown", 0.0
    if side is None:
        side = "front"

    return f"{doc}_{side}", max(conf, 0.6 if side else 0.4)


def pair_documents(filtered: list[tuple[str, dict]]) -> dict[str, dict]:
    """Group classified images into logical documents.

    filtered: list of (doc_type, info_dict). Returns mapping:
        kind -> {"front": path|None, "back": path|None, "front_text": .., "back_text": .., "all_text": ..}
    """
    docs: dict[str, dict] = {}
    for kind, info in filtered:
        entry = docs.setdefault(
            kind,
            {"front": None, "back": None, "front_text": "", "back_text": "", "all_text": ""},
        )
        if kind.endswith("_front"):
            if entry["front"] is None or info["conf"] > entry.get("_front_conf", -1):
                entry["front"] = info["path"]
                entry["front_text"] = info["text"]
                entry["_front_conf"] = info["conf"]
        elif kind.endswith("_back"):
            if entry["back"] is None or info["conf"] > entry.get("_back_conf", -1):
                entry["back"] = info["path"]
                entry["back_text"] = info["text"]
                entry["_back_conf"] = info["conf"]
    for e in docs.values():
        e["all_text"] = e["front_text"] + "\n" + e["back_text"]
        e.pop("_front_conf", None)
        e.pop("_back_conf", None)
    return docs
