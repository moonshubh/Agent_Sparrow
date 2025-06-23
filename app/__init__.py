import os
from pathlib import Path
from dotenv import load_dotenv

# Construct the path to the .env file in the project root
# __file__ is the path to app/__init__.py
# Path(__file__).resolve().parent is the 'app' directory
# Path(__file__).resolve().parent.parent is the project root (MB-Sparrow-main)
env_path = Path(__file__).resolve().parent.parent / ".env"

print(f"--- [app/__init__.py] Attempting to load .env file from: {env_path} ---")
if env_path.is_file():
    load_dotenv(dotenv_path=env_path, override=True)
    print(f"--- [app/__init__.py] Successfully loaded .env file: {env_path} ---")
    if 'GEMINI_API_KEY' in os.environ:
        print("--- [app/__init__.py] GEMINI_API_KEY IS found in os.environ immediately after load. ---")
    else:
        print("--- [app/__init__.py] WARNING: GEMINI_API_KEY NOT found in os.environ immediately after load. ---")
        print("--- [app/__init__.py] Dumping all environment variables for debugging: ---")
        for key, value in os.environ.items():
            print(f"    {key} = {value}")
        print("--- [app/__init__.py] End of environment variable dump. ---")
else:
    print(f"--- [app/__init__.py] ERROR: .env file not found at {env_path}. Please ensure it exists. ---")
