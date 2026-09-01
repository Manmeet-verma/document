"""Extraction of structured fields from Aadhaar and RC OCR text.

Every field is returned with a status:
    "detected"            -> high-confidence parsed value
    "verification required" -> found plausible raw value but not fully certain
    "not detected"        -> nothing found

No guessed/invented values are ever returned.
"""

from __future__ import annotations

import re

NOT_DETECTED = "Not Detected"
VERIF_REQ = "Verification Required"


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :|-–—")


# --------------------------------------------------------------------------
# Aadhaar
# --------------------------------------------------------------------------
AADHAAR_12 = re.compile(r"\b(?:\d{4}[\s]?\d{4}[\s]?\d{4}|\d{12})\b")

AADHAAR_NAME_PATTERNS = [
    re.compile(r"^\s*name\s*[:.]?\s*([A-Z][A-Za-z'. ]+)$", re.M | re.I),
    re.compile(r"\bn(?:a|o)me\s*:\s*([A-Z][A-Za-z'. ]+)", re.I),
]

DOB_PATTERNS = [
    re.compile(r"\b(do[bh]|date\s*of\s*birth)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", re.I),
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2})\b"),
]

GENDER_PATTERNS = [
    re.compile(r"\bgender\s*:\s*(\w+)\b", re.I),
    re.compile(r"\b(male|female|transgender)\b", re.I),
]

FATHER_PATTERNS = [
    re.compile(r"\bfather\s*[:.]?\s*([A-Z][A-Za-z'. ]+)", re.I),
    re.compile(r"\bhusband\s*[:.]?\s*([A-Z][A-Za-z'. ]+)", re.I),
]


def _name_from_lines(text: str) -> tuple[str, str]:
    for pat in AADHAAR_NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = _clean(m.group(1))
            if re.fullmatch(r"(?:name|aadhaar|date of birth|gender|father|mother|address)", name, re.I):
                continue
            return name, "detected"
    for line in text.splitlines():
        line = line.strip()
        if (re.fullmatch(r"[A-Z][A-Za-z'. ]{2,60}", line)
                and not re.search(r"\d", line)
                and line.lower() not in ("government of india", "unique identification authority")):
            return line, VERIF_REQ
    return NOT_DETECTED, "not detected"


def extract_aadhaar(text: str) -> dict:
    fields: dict[str, dict] = {}

    m = AADHAAR_12.search(text)
    if m:
        aadhaar = re.sub(r"\s", "", m.group(0))
        fields["aadhaar_number"] = {"value": aadhaar, "status": "detected"}
    else:
        fields["aadhaar_number"] = {"value": NOT_DETECTED, "status": "not detected"}

    name, status = _name_from_lines(text)
    fields["name"] = {"value": name, "status": status}

    dob = NOT_DETECTED
    dob_status = "not detected"
    for pat in DOB_PATTERNS:
        m = pat.search(text)
        if m:
            dob = m.group(2) if m.lastindex == 2 else m.group(1)
            dob = _clean(dob)
            dob_status = "detected"
            break
    fields["date_of_birth"] = {"value": dob, "status": dob_status}

    gender = NOT_DETECTED
    g_status = "not detected"
    for pat in GENDER_PATTERNS:
        m = pat.search(text)
        if m:
            v = _clean(m.group(1)).title()
            if v.lower() in ("male", "female", "m", "f", "transgender"):
                gender = "Male" if v[:1].lower() == "m" and v != "female" else "Female" if v[:1].lower() == "f" else v
                g_status = "detected"
                break
    fields["gender"] = {"value": gender, "status": g_status}

    father = NOT_DETECTED
    f_status = "not detected"
    for pat in FATHER_PATTERNS:
        m = pat.search(text)
        if m:
            possible = _clean(m.group(1))
            if possible.lower() == fields["name"]["value"].lower():
                continue
            father = possible
            f_status = "detected"
            break
    fields["father_name"] = {"value": father, "status": f_status}

    return fields


# --------------------------------------------------------------------------
# RC
# --------------------------------------------------------------------------
RC_NO = re.compile(r"\b(?:rc\s*(?:no|number)?\s*[:.]?\s*)([A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{4})\b", re.I)
RC_NO_ALT = re.compile(r"\b([A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{3,4})\b")

CHASSIS = re.compile(r"\bchassis\s*(?:no\.?|number|n[oa]\.?)?\s*[:.]?\s*([A-Z0-9]{10,25})\b", re.I)
ENGINE = re.compile(r"\bengine\s*(?:no\.?|number|n[oa]\.?)?\s*[:.]?\s*([A-Z0-9]{5,25})\b", re.I)

OWNER_PATTERNS = [
    re.compile(r"\b(?:owner['\u2019]?s?\s*name|registered\s*owner)\s*[:.]?\s*([A-Z][A-Za-z'. ]+)", re.I),
    re.compile(r"\b(?:name\s*of\s*owner|owner)\s*:\s*([A-Z][A-Za-z'. ]+)", re.I),
]

MAKE_MODEL = re.compile(r"\b(?:maker\s*[:.]?\s*|model\s*[:.]?\s*|make\s*[:.]?\s*)([A-Za-z0-9 \-]{2,30})\b", re.I)

DATE_PATTERNS = {
    "reg": [re.compile(r"\b(?:regd?\s*(?:on|date)?\s*[:.]?\s*)(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", re.I)],
    "insurance": [re.compile(r"\b(?:insurance\s*(?:upto|valid\s*upto|expiry)?\s*[:.]?\s*...?)(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", re.I),
                  re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(?:insurance|policy)\b", re.I)],
    "fit": [re.compile(r"\b(?:fitness\s*upto|fitness)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", re.I),
            re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+fitness\b", re.I)],
    "tax": [re.compile(r"\b(?:tax\s*upto|tax)\s*[:.]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", re.I)],
}

EXCLUDE_NAMES = {
    "not", "none", "nil", "na", "n/a", "unknown", "government of india",
    "registration certificate", "service", "details", "owner", "name",
}


def _extract_date(patterns: list[re.Pattern], text: str) -> tuple[str, str]:
    for pat in patterns:
        m = pat.search(text)
        if m:
            d = _clean(m.group(1))
            if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", d):
                return d, "detected"
    return NOT_DETECTED, "not detected"


def extract_rc(text: str) -> dict:
    fields: dict[str, dict] = {}

    rc_no = NOT_DETECTED
    rc_status = "not detected"
    m = RC_NO.search(text)
    if m:
        rc_no = _clean(m.group(1))
        rc_status = "detected"
    else:
        m = RC_NO_ALT.search(text)
        if m:
            rc_no = _clean(m.group(1))
            rc_status = VERIF_REQ
    fields["registration_number"] = {"value": rc_no, "status": rc_status}

    ch = NOT_DETECTED
    c_stat = "not detected"
    m = CHASSIS.search(text)
    if m:
        ch = _clean(m.group(1))
        c_stat = "detected"
    fields["chassis_number"] = {"value": ch, "status": c_stat}

    en = NOT_DETECTED
    e_stat = "not detected"
    m = ENGINE.search(text)
    if m:
        en = _clean(m.group(1))
        e_stat = "detected"
    fields["engine_number"] = {"value": en, "status": e_stat}

    owner = NOT_DETECTED
    o_stat = "not detected"
    for pat in OWNER_PATTERNS:
        m = pat.search(text)
        if m:
            v = _clean(m.group(1))
            if v.lower() not in EXCLUDE_NAMES and len(v) > 1:
                owner = v
                o_stat = "detected"
                break
    fields["vehicle_owner_name"] = {"value": owner, "status": o_stat}

    fields["make_model"] = {"value": NOT_DETECTED, "status": "not detected"}
    m = MAKE_MODEL.search(text)
    if m:
        v = _clean(m.group(1))
        if v.lower() not in EXCLUDE_NAMES and len(v) > 1:
            fields["make_model"]["value"] = v
            fields["make_model"]["status"] = VERIF_REQ

    reg_date, rs = _extract_date(DATE_PATTERNS["reg"], text)
    fields["registration_date"] = {"value": reg_date, "status": rs}

    ins_date, ins = _extract_date(DATE_PATTERNS["insurance"], text)
    fields["insurance_valid_upto"] = {"value": ins_date, "status": ins}

    fit_date, fit = _extract_date(DATE_PATTERNS["fit"], text)
    fields["fitness_upto"] = {"value": fit_date, "status": fit}

    tax_date, tax = _extract_date(DATE_PATTERNS["tax"], text)
    fields["tax_valid_upto"] = {"value": tax_date, "status": tax}

    return fields


# --------------------------------------------------------------------------
# Final merge into one row
# --------------------------------------------------------------------------
AADHAAR_COLUMNS = [
    ("name", "Name"),
    ("aadhaar_number", "Aadhaar Number"),
    ("date_of_birth", "Date of Birth"),
    ("gender", "Gender"),
    ("father_name", "Father/Spouse Name"),
]

RC_COLUMNS = [
    ("registration_number", "Vehicle Registration Number"),
    ("vehicle_owner_name", "Vehicle Owner Name"),
    ("chassis_number", "Chassis Number"),
    ("engine_number", "Engine Number"),
    ("make_model", "Make / Model"),
    ("registration_date", "Registration Date"),
    ("insurance_valid_upto", "Insurance Valid Upto"),
    ("fitness_upto", "Fitness Valid Upto"),
    ("tax_valid_upto", "Tax Valid Upto"),
]


def extract_document(doc_type: str, doc: dict) -> dict[str, dict]:
    """Given a paired document dict, return ordered field dicts."""
    text = doc.get("all_text", "")
    if doc_type == "aadhaar":
        return extract_aadhaar(text)
    return extract_rc(text)


def merge_row(person_id: str, docs: dict) -> dict:
    """Merge a person's documents into the final excel-row dictionary."""
    row: dict = {
        "person_id": person_id,
        "aadhaar_images": "",
        "rc_images": "",
    }

    aad_front = docs.get("aadhaar_front") or {}
    aad_back = docs.get("aadhaar_back") or {}
    rc_front = docs.get("rc_front") or {}
    rc_back = docs.get("rc_back") or {}

    aad_combined = _combine(aad_front, aad_back)
    rc_combined = _combine(rc_front, rc_back)

    row["aadhaar_images"] = "\n".join(
        p for p in (aad_front.get("front"), aad_back.get("back")) if p
    )
    row["rc_images"] = "\n".join(
        p for p in (rc_front.get("front"), rc_back.get("back")) if p
    )

    if aad_combined:
        aad_fields = extract_document("aadhaar", aad_combined)
        for key, _header in AADHAAR_COLUMNS:
            row[key] = aad_fields.get(key, {})

    if rc_combined:
        rc_fields = extract_document("rc", rc_combined)
        for key, _header in RC_COLUMNS:
            row[key] = rc_fields.get(key, {})

    return row


def _combine(*parts: dict) -> dict | None:
    combined = {"all_text": ""}
    added = False
    for part in parts:
        if not part:
            continue
        combined["all_text"] += "\n" + (part.get("all_text") or "")
        combined["front"] = combined.get("front") or part.get("front")
        combined["back"] = combined.get("back") or part.get("back")
        combined["front_text"] = combined.get("front_text") or part.get("front_text")
        combined["back_text"] = combined.get("back_text") or part.get("back_text")
        added = True
    return combined if added else None


def field_value(field: dict | None) -> str:
    if not field:
        return NOT_DETECTED
    return field.get("value", NOT_DETECTED)
