"""
Docket Local Development Runner
Launches the FastAPI backend (port 8000) and React/Vite frontend (port 5173).
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"


def banner():
    print("=" * 70)
    print("  DOCKET - Evidence Reconciliation & Controlled-Decision Agent")
    print("  PayPal AI Hackathon | AG Grid Partner Track")
    print("=" * 70)
    print("  * Backend API:       http://127.0.0.1:8000")
    print("  * Swagger Docs:      http://127.0.0.1:8000/docs")
    print("  * Frontend UI:       http://localhost:5173")
    print("  * Evaluation Matrix: http://127.0.0.1:8000/api/eval/scorecard")
    print("=" * 70)


def start_backend():
    cmd = [sys.executable, "-m", "uvicorn", "docket.api.app:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000", "--reload"]
    print("[BACKEND] Starting FastAPI uvicorn server on http://127.0.0.1:8000...")
    return subprocess.Popen(cmd, cwd=str(ROOT_DIR))


def start_frontend():
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    cmd = [npm_cmd, "run", "dev"]
    print("[FRONTEND] Starting Vite React dev server on http://localhost:5173...")
    return subprocess.Popen(cmd, cwd=str(FRONTEND_DIR), shell=(sys.platform == "win32"))


def main():
    parser = argparse.ArgumentParser(description="Run Docket local dev environment.")
    parser.add_argument("--backend-only", action="store_true", help="Launch FastAPI backend only.")
    parser.add_argument("--frontend-only", action="store_true", help="Launch Vite React frontend only.")
    args = parser.parse_args()

    banner()

    processes = []

    try:
        if args.backend_only:
            p_back = start_backend()
            processes.append(p_back)
            p_back.wait()
        elif args.frontend_only:
            p_front = start_frontend()
            processes.append(p_front)
            p_front.wait()
        else:
            p_back = start_backend()
            processes.append(p_back)
            time.sleep(1.5)  # Let backend initialize
            p_front = start_frontend()
            processes.append(p_front)

            print("\n[DOCKET] All systems running. Press Ctrl+C to terminate all services.\n")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        print("\n[DOCKET] Gracefully shutting down services...")
        for p in processes:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[DOCKET] All services stopped.")


if __name__ == "__main__":
    main()

