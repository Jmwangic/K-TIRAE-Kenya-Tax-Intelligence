import os
import subprocess
import sys
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ["DATABASE_URL"]
PORT = os.environ.get("PORT", "8000")


def initialise_database() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        for path in sorted((ROOT / "db").glob("*.sql")):
            connection.execute(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    initialise_database()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            PORT,
        ],
        cwd=ROOT,
        check=True,
    )
