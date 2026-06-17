"""Standalone seeding script: `python -m scripts.seed`."""
from __future__ import annotations

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed.seed_data import run_all


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        run_all(db)
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
