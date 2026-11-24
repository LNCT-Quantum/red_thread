"""Red Thread backend entry point.

Run from the ``backend/`` directory::

    uvicorn main:app --host 127.0.0.1 --port 8000      # or: python main.py

All configuration comes from environment variables (see ``backend/.env.example``).
"""

from __future__ import annotations

from api.app import create_app
from api.config import Settings

app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run("main:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower())
