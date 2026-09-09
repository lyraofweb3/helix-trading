"""Railway-safe entrypoint: reads PORT from env."""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, proxy_headers=True)
