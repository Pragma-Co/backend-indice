def serialize_upload_result(result):
    return {
        "temp_file_id": result["temp_file_id"],
        "original_name": result["original_name"],
        "file_size": result["file_size"],
        "inferred_type": result["inferred_type"],
    }