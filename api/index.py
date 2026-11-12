import os
import sys
import shutil
from pathlib import Path

# Add project root to sys.path so 'docket' package can be imported
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Serverless environment handling: /tmp is the only writable directory on Vercel
audit_log_path = None
db_path = None

if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    tmp_dir = Path("/tmp")

    # 1. Database
    tmp_db = tmp_dir / "docket.db"
    src_db = root_dir / "artifacts" / "docket.db"
    if src_db.exists() and not tmp_db.exists():
        try:
            shutil.copy2(src_db, tmp_db)
        except Exception as e:
            print(f"Notice: Failed to copy database to /tmp: {e}")

    db_path = str(tmp_db) if tmp_db.exists() else (str(src_db) if src_db.exists() else None)
    if db_path:
        os.environ["DOCKET_DB_PATH"] = db_path

    # 2. Audit Trail JSONL
    tmp_log = tmp_dir / "audit_trail.jsonl"
    src_log = root_dir / "artifacts" / "audit_trail.jsonl"
    if src_log.exists() and not tmp_log.exists():
        try:
            shutil.copy2(src_log, tmp_log)
        except Exception as e:
            print(f"Notice: Failed to copy audit trail to /tmp: {e}")

    audit_log_path = str(tmp_log) if tmp_log.exists() else (str(src_log) if src_log.exists() else None)

    # In serverless environment, disable continuous background polling threads
    os.environ["DOCKET_DISABLE_BG_SCHEDULER"] = "true"

from docket.api.app import create_app

# Instantiate FastAPI application
app = create_app(db_path=db_path, audit_log_path=audit_log_path)
