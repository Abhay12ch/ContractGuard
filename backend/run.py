"""Universal launcher for the ContractGuard FastAPI backend server.

Works regardless of whether it is launched from the root directory or the backend directory.
"""

import os
import sys
from pathlib import Path

# Always guarantee ContractGuard root is at index 0 of sys.path
CURRENT_FILE = Path(__file__).resolve()
if CURRENT_FILE.parent.name == "backend":
    PROJECT_ROOT = CURRENT_FILE.parent.parent
else:
    PROJECT_ROOT = CURRENT_FILE.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.chdir(str(PROJECT_ROOT))

if __name__ == "__main__":
    import uvicorn
    print(f"[*] Starting ContractGuard backend from: {PROJECT_ROOT}")
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
