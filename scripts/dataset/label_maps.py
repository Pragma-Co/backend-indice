DOCUMENT_TYPE_BY_CATEGORY = {
    "Detail Specification": "SPECIFICATION",
    "Federal Specification": "SPECIFICATION",
    "Performance Specification": "SPECIFICATION",
    "Commercial Item Description (CID)": "COMMERCIAL_ITEM",
    "Defense Handbook": "HANDBOOK",
    "Military Standard": "STANDARD",
    "Military Standard -Standard Practice": "STANDARD",
    "Military Standard -Design Criteria Standard": "STANDARD",
    "Military Standard -Test Method Standard": "STANDARD",
    "Military Standard -Military Standard": "STANDARD",
    "Military Standard -Interface Standard": "STANDARD",
    "Federal Standard": "STANDARD",
    "Air Force/Navy AN": "STANDARD",
    "Air Force/Navy Aeronautical Design Document (AND)": "STANDARD",
}

DISCIPLINE_BY_FSC_GROUP = {
    "16": "MECHANICAL",
    "31": "MECHANICAL",
    "47": "MECHANICAL",
    "53": "MECHANICAL",
    "59": "ELECTRICAL",
    "61": "ELECTRICAL",
    "68": "MATERIALS",
    "80": "MATERIALS",
    "91": "MATERIALS",
    "95": "MATERIALS",
}

FSC_GROUP_LENGTH = 2


class UnmappedLabelError(Exception):
    pass


def document_type_for(doc_category: str) -> str:
    label = DOCUMENT_TYPE_BY_CATEGORY.get(doc_category.strip())
    if label is None:
        raise UnmappedLabelError(f"document category {doc_category!r} has no document type")
    return label


def discipline_for(fsc: str) -> str:
    label = DISCIPLINE_BY_FSC_GROUP.get(fsc.strip()[:FSC_GROUP_LENGTH])
    if label is None:
        raise UnmappedLabelError(f"FSC {fsc!r} has no discipline")
    return label
