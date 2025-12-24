
import json
import os
import sys

# Add the current directory to sys.path so we can import app
sys.path.append(os.getcwd())

from app.main import app

def generate_openapi():
    print("Generating OpenAPI schema...")
    openapi_schema = app.openapi()
    
    output_file = "openapi.json"
    with open(output_file, "w") as f:
        json.dump(openapi_schema, f, indent=2)
    
    print(f"OpenAPI schema saved to {output_file}")

if __name__ == "__main__":
    generate_openapi()
