import re

NOTICE_SUFFIX_PATTERN = re.compile(r"\s+(?:NOT|NOTICE|AMD|AMENDMENT|SUP|SUPP|CHG|CHANGE)\b.*$")
AMENDMENT_NUMBER_PATTERN = re.compile(r"\(\d+\)")
REVISION_LETTERS_PATTERN = re.compile(r"(?<=\d)[A-Z]{1,2}$")


def group_key(document_id: str) -> str:
    key = document_id.strip().upper()
    key = NOTICE_SUFFIX_PATTERN.sub("", key)
    key = AMENDMENT_NUMBER_PATTERN.sub("", key).strip()
    return REVISION_LETTERS_PATTERN.sub("", key)
