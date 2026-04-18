"""Memory HTTP Server entry point.

Usage: python -m Memory.server
"""

import os
import uvicorn

if __name__ == "__main__":
    host = os.getenv("MEMORY_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MEMORY_SERVER_PORT", "8001"))

    uvicorn.run(
        "Memory.server.app:app",
        host=host,
        port=port,
        log_level="info",
    )
