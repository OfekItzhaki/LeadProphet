"""Reset and seed the isolated Playwright database."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.e2e_seed import reset_e2e_database  # noqa: E402


if __name__ == "__main__":
    reset_e2e_database()
    print("E2E database ready")
