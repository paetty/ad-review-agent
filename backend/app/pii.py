from __future__ import annotations
import re

SENSITIVE_FIELD_TOKENS = {"imei", "phone", "mobile", "手机号", "姓名", "name", "身份证", "id_card", "email", "device_id"}
SENSITIVE_FIELD_SUBSTRINGS = {"手机号", "姓名", "身份证"}
PATTERNS = {
    "phone": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "id_card": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "imei": re.compile(r"(?<!\d)\d{15}(?!\d)"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}

def detect_sensitive_columns(columns: list[str]) -> list[str]:
    sensitive=[]
    for column in columns:
        normalized=column.strip().lower()
        # English tokens are exact field names so harmless columns such as
        # image_filename are not rejected merely because they contain "name".
        if normalized in SENSITIVE_FIELD_TOKENS or any(token in normalized for token in SENSITIVE_FIELD_SUBSTRINGS):
            sensitive.append(column)
    return sensitive

def detect_pii_text(text: str) -> list[str]:
    return [name for name, pattern in PATTERNS.items() if pattern.search(text or "")]

