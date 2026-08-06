from __future__ import annotations

import os

from ui.server import run


if __name__ == "__main__":
    run(port=int(os.getenv("UI_PORT", "8765")))
