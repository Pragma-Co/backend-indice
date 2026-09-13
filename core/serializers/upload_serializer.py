def serialize_upload_result(result):
    return {
        "temp_file_id": result["temp_file_id"],
        "original_name": result["original_name"],
        "file_size": result["file_size"],
        "inferred_type": result["inferred_type"],
        "sha256": result["sha256"],
    }

def serialize_duplicate_result(exc):
    return {
        "duplicate": True,
        "message": "Este arquivo já foi cadastrado anteriormente no sistema.",
        "document": {
            "id": exc.document_id,
            "codigo_ra": exc.codigo_ra,
            "titulo": exc.titulo,
            "status": exc.status,
            "data_upload": exc.data_upload.isoformat() if exc.data_upload else None,
        },
    }

