import os
import sys

import uvicorn

from app import config
from app.main import app

if __name__ == "__main__":
    # pythonw.exe har ingen konsoll: send utskrift til loggfil så feil kan leses
    if sys.stdout is None or sys.stderr is None:
        log = open(config.DATA_DIR / "nexus.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    uvicorn.run(app, host="127.0.0.1", port=config.PORT, log_level="warning")
