"""
scheduler.py — APScheduler long-running process for Railway deployment
All times are Eastern (US/Eastern).

Schedule:
  10:00 AM → Pull slate + send daily summary
  12:00 PM → First analysis run + BET alerts
   3:00 PM → Re-run analysis (catch line movement)
   6:00 PM → Final pre-game run (late lines + scratches)
  11:00 PM → Results logging reminder
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import time
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron      import CronTrigger

from data.database   import init_db, get_connection
from data.bdl_client  import BallDontLieClient
from data.odds_client import OddsAPIClient
from alerts.telegram  import TelegramNotifier
import main as pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("scheduler")

TIMEZONE = "US/Eastern"

# ─── Scheduled jobs ──────────────────────────────────────────────────────────

def job_morning_slate():
    """10 AM — Pull fresh odds, send daily summary to Telegram."""
    log.info("10 AM job started: morning slate pull")
    try:
        init_db()
        conn     = get_connection()
        notifier = TelegramNotifier()
        slate_size = pipeline.sync_odds(conn)
        conn.close()

        # Estimate bets based on historical hit rate (~15% of slate)
        expected = max(1, slate_size // 7)
        notifier.send_daily_summary(slate_size=slate_size, expected_bets=expected)
        log.info(f"Morning summary sent — {slate_size} games on slate")
    except Exception as e:
        log.error(f"Morning slate job failed: {e}")
        TelegramNotifier().send_error_alert()

def job_analysis(label: str):
    """Generic analysis run — syncs odds, evaluates, sends alerts."""
    log.info(f"{label} analysis run started")
    try:
        pipeline.main()
        log.info(f"{label} run complete")
    except Exception as e:
        log.error(f"{label} run failed: {e}")
        TelegramNotifier().send_error_alert()

def job_noon():
    job_analysis("12 PM")

def job_3pm():
    job_analysis("3 PM")

def job_6pm():
    job_analysis("6 PM")

def job_night_reminder():
    """11 PM — Results logging reminder."""
    log.info("11 PM reminder sent")
    try:
        TelegramNotifier().send_log_reminder()
    except Exception as e:
        log.error(f"Night reminder failed: {e}")

# ─── Scheduler setup ─────────────────────────────────────────────────────────

def main():
    log.info("CBB Betting Bot scheduler starting…")
    init_db()

    scheduler = BlockingScheduler(timezone=TIMEZONE)

    # 10:00 AM — morning slate pull + summary
    scheduler.add_job(job_morning_slate, CronTrigger(hour=10, minute=0, timezone=TIMEZONE), id="morning_slate")
    # 12:00 PM — first analysis
    scheduler.add_job(job_noon,          CronTrigger(hour=12, minute=0, timezone=TIMEZONE), id="noon_analysis")
    # 3:00 PM — mid-day re-run
    scheduler.add_job(job_3pm,           CronTrigger(hour=15, minute=0, timezone=TIMEZONE), id="3pm_analysis")
    # 6:00 PM — final pre-game run
    scheduler.add_job(job_6pm,           CronTrigger(hour=18, minute=0, timezone=TIMEZONE), id="6pm_analysis")
    # 11:00 PM — results reminder
    scheduler.add_job(job_night_reminder,CronTrigger(hour=23, minute=0, timezone=TIMEZONE), id="night_reminder")

    log.info("Scheduler running. Jobs: 10 AM, 12 PM, 3 PM, 6 PM, 11 PM Eastern.")
    log.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")

if __name__ == "__main__":
    main()
