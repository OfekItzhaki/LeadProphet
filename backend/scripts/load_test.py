"""Measure deterministic local analysis throughput for existing unprocessed leads."""

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.models import Lead, User  # noqa: E402
from app.services.ai_pipeline import LeadPipeline  # noqa: E402


async def run(email: str, limit: int) -> None:
    timings: list[float] = []
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email.lower()).first()
        if not user: raise SystemExit(f"User not found: {email}. Run seed_demo_data.py first.")
        leads = db.query(Lead).filter(Lead.user_id == user.id, Lead.status == "new", Lead.duplicate_of_id.is_(None)).limit(limit).all()
        pipeline = LeadPipeline(db)
        for lead in leads:
            started = time.perf_counter(); await pipeline.process_lead(lead); timings.append(time.perf_counter() - started)
    total = sum(timings)
    print(f"Processed {len(timings)} leads in {total:.2f}s")
    if timings: print(f"mean={statistics.mean(timings):.3f}s median={statistics.median(timings):.3f}s throughput={len(timings) / total:.2f} leads/s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--email", default="demo@leadprophet.local"); parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(); asyncio.run(run(args.email, max(1, args.limit)))
