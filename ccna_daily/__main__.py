"""Run the server: python -m ccna_daily (host and port from CCNA_HOST / CCNA_PORT)."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "ccna_daily.app:app",
        host=os.environ.get("CCNA_HOST", "0.0.0.0"),
        port=int(os.environ.get("CCNA_PORT", "8080")),
        proxy_headers=True,
    )
