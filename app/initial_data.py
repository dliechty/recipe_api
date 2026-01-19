
import logging
from sqlalchemy.orm import Session

from app import crud, models
from app.db.session import SessionLocal
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db(db: Session) -> None:
    if not settings.FIRST_SUPERUSER_EMAIL or not settings.FIRST_SUPERUSER_PASSWORD:
        logger.info("First superuser not configured, skipping creation.")
        return

    # Check if superuser exists
    user = crud.get_user_by_email(db, email=settings.FIRST_SUPERUSER_EMAIL)
    if user:
        logger.info(f"Superuser {settings.FIRST_SUPERUSER_EMAIL} already exists.")
    else:
        logger.info(f"Creating superuser {settings.FIRST_SUPERUSER_EMAIL}...")
        import uuid
        user = models.User(
            id=uuid.uuid4(),
            email=settings.FIRST_SUPERUSER_EMAIL,
            hashed_password=crud.get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
            first_name=settings.FIRST_SUPERUSER_FIRST_NAME,
            last_name=settings.FIRST_SUPERUSER_LAST_NAME,
            is_admin=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Superuser created successfully.")

def main() -> None:
    db = SessionLocal()
    init_db(db)

if __name__ == "__main__":
    main()
