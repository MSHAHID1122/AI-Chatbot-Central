from database.connection import engine
from database.models import Base

def init():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init()