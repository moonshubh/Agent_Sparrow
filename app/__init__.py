from pathlib import Path
from dotenv import load_dotenv

# Construct the path to the .env file in the project root
# __file__ is the path to app/__init__.py
# Path(__file__).resolve().parent is the 'app' directory
# Path(__file__).resolve().parent.parent is the project root (MB-Sparrow-main)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.is_file():
    load_dotenv(dotenv_path=env_path, override=True)

# Import settings after environment variables are loaded
from app.core.settings import settings  # noqa: F401,E402
