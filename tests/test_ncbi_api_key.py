from config import NCBI_API_KEY

print("\n=== NCBI API Key Configuration Test ===")

if NCBI_API_KEY:
    print("SUCCESS: NCBI API key loaded successfully.")
    print("Key length:", len(NCBI_API_KEY))
else:
    print("ERROR: NCBI API key was not found.")