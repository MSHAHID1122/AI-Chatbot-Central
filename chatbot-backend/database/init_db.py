# db/init_db.py
import logging
from database import engine, Base

logger = logging.getLogger(__name__)

def create_all():
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Done.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_all()