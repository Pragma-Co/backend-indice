def serialize_suggestion(result: dict) -> dict:
    return {
        "title": result["title"],
        "description": result["description"],
        "project": result["project"],
        "discipline": result["discipline"],
        "document_type": result["document_type"],
        "area": result["area"],
    }
