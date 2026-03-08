import json
import os
from datetime import datetime


def save_session_audit(session_data, log_dir="logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_name = f"session_audit_{timestamp}.json"
    file_path = os.path.join(log_dir, file_name)

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(session_data, file, indent=2)

    return file_path