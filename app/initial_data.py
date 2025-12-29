
import logging
from sqlalchemy.orm import Session

from app import crud, schemas
from app.db.session import SessionLocal
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db(db: Session) -> None:
    # Check if superuser exists
    user = crud.get_user_by_email(db, email=settings.FIRST_SUPERUSER_EMAIL)
    if user:
        logger.info(f"Superuser {settings.FIRST_SUPERUSER_EMAIL} already exists.")
    else:
        logger.info(f"Creating superuser {settings.FIRST_SUPERUSER_EMAIL}...")
        user_in = schemas.UserCreate(
            email=settings.FIRST_SUPERUSER_EMAIL,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            first_name="Initial",
            last_name="Superuser"
        )
        user = crud.create_user(db, user_in)
        user.is_admin = True
        user.is_active = True
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Superuser created successfully.")

def main() -> None:
    db = SessionLocal()
    init_db(db)

if __name__ == "__main__":
    main()
