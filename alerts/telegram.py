import os
import asyncio
from datetime import datetime
from telegram import Bot

class TelegramNotifier:
    def __init__(self):
        token   = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.bot = Bot(token=token) if token else None

    async def _send(self, text):
        if not self.bot or not self.chat_id:
            print(f"[Telegram disabled] {text}")
            return
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode='HTML')
        except Exception as e:
            print(f"Telegram send error: {e}")

    def _fire(self, text):
        asyncio.run(self._send(text))

    # ─── Error / System Alerts ────────────────────────────────────────────────

    def send_error_alert(self):
        self._fire("🚨 <b>BOT ERROR</b> – Data pull failed, no picks generated")

    # ─── Daily Schedule ───────────────────────────────────────────────────────

    def send_daily_summary(self, slate_size: int, expected_bets: int):
        date = datetime.now().strftime('%A, %B %d')
        msg  = (
            f"📅 <b>CBB Daily Summary — {date}</b>\n\n"
            f"🏀 Games on slate today: <b>{slate_size}</b>\n"
            f"🎯 Expecting ~<b>{expected_bets}</b> BET alerts\n\n"
            f"✅ Bot is running\n"
            f"🔄 Next analysis run: 12:00 PM EST"
        )
        self._fire(msg)

    def send_log_reminder(self):
        self._fire(
            "📝 <b>Results Reminder</b>\n"
            "Please log today's game outcomes so we can track our season record!"
        )

    def send_status_update(self, last_run: str, picks_today: int, season_ats_w: int, season_ats_l: int, next_run: str):
        ats_pct = (season_ats_w / (season_ats_w + season_ats_l) * 100) if (season_ats_w + season_ats_l) > 0 else 0
        msg = (
            f"✅ <b>Bot is running</b>\n"
            f"📅 Last run: <b>{last_run}</b>\n"
            f"🎯 Picks today: <b>{picks_today} BETs sent</b>\n"
            f"📊 Season record: <b>{season_ats_w}-{season_ats_l} ATS ({ats_pct:.0f}%)</b>\n"
            f"🔄 Next run: <b>{next_run}</b>"
        )
        self._fire(msg)

    # ─── BET Alert ────────────────────────────────────────────────────────────

    def send_bet_alert(
        self, game_id, matchup, commence_time,
        market_spread, proj_spread,
        market_total, proj_total,
        confidence, reasons, signals=0,
        conn=None
    ):
        # Duplicate guard
        if conn:
            from datetime import date as _date
            today = _date.today().isoformat()
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM notified_games WHERE game_id = ? AND notification_date = ?",
                (game_id, today)
            )
            if cur.fetchone():
                return  # already sent today

        # Format tip time
        try:
            from datetime import datetime as dt
            tip = dt.fromisoformat(commence_time.replace('Z', '+00:00'))
            time_str = tip.strftime('%I:%M %p EST')
        except Exception:
            time_str = str(commence_time)

        teams = matchup.split(' @ ')
        away_team = teams[0]
        home_team = teams[1] if len(teams) > 1 else "Home"

        # Spread direction
        spread_edge = proj_spread - market_spread
        bet_spread_side = home_team if spread_edge < 0 else away_team
        bet_total_side  = "OVER" if proj_total > market_total else "UNDER"

        msg = (
            f"🏀 <b>ALERT: {matchup}</b>\n"
            f"🕐 Tip: {time_str}\n\n"
            f"📊 <b>SPREAD:</b> {market_spread}\n"
            f"   My Line: {proj_spread:.1f} → ✅ BET {bet_spread_side}\n\n"
            f"📈 <b>TOTAL:</b> {market_total}\n"
            f"   My Total: {proj_total:.1f} → ✅ BET {bet_total_side}\n\n"
            f"💰 <b>MONEYLINE:</b> PASS\n\n"
            f"⚡ <b>Confidence:</b> {confidence} ({signals}/4 signals)\n"
            f"📝 {reasons}"
        )
        self._fire(msg)

        # Mark as sent
        if conn:
            cur.execute(
                "INSERT OR IGNORE INTO notified_games (game_id, notification_date) VALUES (?, ?)",
                (game_id, today)
            )
            conn.commit()
