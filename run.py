"""Convenience launcher so the app runs correctly regardless of CWD.

The application uses package-relative imports (``from .capabilities import ...``)
in ``app/``. Those only resolve when the app is loaded as the ``app.main``
package from the *project root* — NOT by ``cd app`` then ``uvicorn main:app``
(which strips the package context and raises
``ImportError: attempted relative import with no known parent package``).

Run any of these from the project root:

    python run.py                      # this launcher (recommended)
    uvicorn app.main:app --reload      # equivalent explicit form

Optional env vars: HOST (default 127.0.0.1), PORT (default 8000),
RELOAD ("1"/"0", default "1").
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

# Ensure the project root (this file's directory) is importable as the parent
# package, so ``app.main`` resolves even if launched from elsewhere.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    # Cloud Run sets K_SERVICE and PORT. Bind all interfaces or the proxy
    # cannot reach the process. Local runs stay on localhost unless HOST is set.
    if os.environ.get("K_SERVICE"):
        host = os.environ.get("HOST", "0.0.0.0")
    else:
        host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8001"))
    reload = os.environ.get("RELOAD", "1") not in ("0", "false", "False")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
