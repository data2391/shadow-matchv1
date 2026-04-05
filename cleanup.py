"""
core/cleanup.py  —  Upload folder janitor
Deletes files older than `max_age_hours` from the web upload directory.
Run at startup and optionally schedule with APScheduler.
"""

import os
import time
from pathlib import Path
from cli.interface import print_status


class CleanupManager:
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

    def __init__(self, upload_dir: str = "web/uploads", max_age_hours: float = 2.0):
        self.upload_dir   = Path(upload_dir)
        self.max_age_secs = max_age_hours * 3600
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> int:
        """Delete stale uploads. Returns number of files deleted."""
        now     = time.time()
        deleted = 0
        total_freed = 0

        for fp in self.upload_dir.iterdir():
            if fp.suffix.lower() not in self.ALLOWED_EXTENSIONS:
                continue
            age = now - fp.stat().st_mtime
            if age > self.max_age_secs:
                size = fp.stat().st_size
                fp.unlink(missing_ok=True)
                total_freed += size
                deleted += 1

        if deleted:
            freed_mb = total_freed / (1024 * 1024)
            print_status(
                f"Cleanup: removed {deleted} stale upload(s) — freed {freed_mb:.2f} MB",
                "success"
            )
        return deleted

    def wipe_all(self) -> int:
        """Nuclear option: delete ALL images in upload dir (use with -S)."""
        deleted = 0
        for fp in self.upload_dir.iterdir():
            if fp.suffix.lower() in self.ALLOWED_EXTENSIONS:
                fp.unlink(missing_ok=True)
                deleted += 1
        if deleted:
            print_status(f"Stealth wipe: {deleted} upload(s) purged.", "success")
        return deleted

    def schedule(self, interval_hours: float = 1.0):
        """Start APScheduler background job for automatic cleanup."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            scheduler = BackgroundScheduler()
            scheduler.add_job(self.run, "interval", hours=interval_hours)
            scheduler.start()
            print_status(f"Auto-cleanup scheduled every {interval_hours}h", "info")
            return scheduler
        except ImportError:
            print_status("APScheduler not installed (optional). pip install apscheduler", "warning")
            return None
