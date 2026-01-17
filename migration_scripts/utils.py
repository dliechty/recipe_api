import os
import subprocess
import sys
from io import StringIO
import pandas as pd
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User

# Database path - relative to project root
DB_PATH = "migrate_data/Recipes.accdb"

def run_mdb_export(table_name: str) -> pd.DataFrame:
    """Exports a table from the Access database to a Pandas DataFrame."""
    # print(f"Exporting {table_name}...")
    try:
        # Check if DB exists
        if not os.path.exists(DB_PATH):
             print(f"Database file not found at {DB_PATH}")
             sys.exit(1)

        result = subprocess.run(
            ["mdb-export", DB_PATH, table_name],
            capture_output=True,
            text=True,
            check=True
        )
        return pd.read_csv(StringIO(result.stdout))
    except subprocess.CalledProcessError as e:
        print(f"Error exporting {table_name}: {e}")
        # print(e.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {table_name}: {e}")
        sys.exit(1)

def get_or_create_user(session: Session, email: str = "admin@example.com") -> User:
    """Gets an existing user or returns the first admin user."""
    user = session.query(User).filter(User.email == email).first()
    if user:
        return user
    
    user = session.query(User).filter(User.is_admin == True).first()
    if user:
        # print(f"User {email} not found. Using admin: {user.email}")
        return user
        
    print("No users found. Please create a user first.")
    sys.exit(1)

def clean_text(text):
    if pd.isna(text):
        return None
    s = str(text).strip()
    return s if s else None
