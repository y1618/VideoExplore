import json
from pathlib import Path

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Taxonomy

TAXONOMY_FILE = Path(__file__).resolve().parents[2] / "seed" / "taxonomy.json"


def seed_taxonomy_if_empty() -> int:
    """起動時に語彙(taxonomy)が空なら seed を投入する。"""
    db = SessionLocal()
    try:
        count = db.scalar(select(func.count()).select_from(Taxonomy))
        if count:
            return 0
        data = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
        for row in data:
            db.add(
                Taxonomy(
                    tag=row["tag"],
                    aliases=row.get("aliases", []),
                    category=row.get("category"),
                )
            )
        db.commit()
        return len(data)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
