import os
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Set DEBUG=true in .env to show detailed HTTP response timings.
DEBUG = os.getenv("DEBUG", "false").strip().lower() == "true"

# NCBI API configuration
NCBI_API_KEY = os.getenv("NCBI_API_KEY")
NCBI_EMAIL = os.getenv("NCBI_EMAIL")
