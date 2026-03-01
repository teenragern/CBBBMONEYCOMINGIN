"""
main.py — CBB Betting Bot full pipeline
Handles data sync, analysis, and alerts in one call.
Called directly by scheduler.py on each scheduled run.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from data.database   import get_connection, init_db
from data.bdl_client  import BallDontLieClient
from data.odds_client import OddsAPIClient
from models.bet_logic import BetDecisionEngine
from alerts.telegram  import TelegramNotifier

# ─── Sync helpers ─────────────────────────────────────────────────────────────

def sync_odds(conn):
    odds_client = OddsAPIClient()
    games = odds_client.get_cbb_odds()
    if not games:
        return 0

    cursor = conn.cursor()
    inserted = 0
    for g in games:
        game_id      = g.get('id')
        home_team    = g.get('home_team')
        away_team    = g.get('away_team')
        commence     = g.get('commence_time', '')

        spread_home = total_over = opening_spread = opening_total = None

        for bm in g.get('bookmakers', []):
            for mkt in bm.get('markets', []):
                if mkt['key'] == 'spreads':
                    for outcome in mkt.get('outcomes', []):
                        if outcome['name'] == home_team:
                            curr = outcome.get('point')
                            if spread_home is None:
                                spread_home = curr
                            if opening_spread is None:
                                opening_spread = curr
                elif mkt['key'] == 'totals':
                    for outcome in mkt.get('outcomes', []):
                        if outcome['name'] == 'Over':
                            curr = outcome.get('point')
                            if total_over is None:
                                total_over = curr
                            if opening_total is None:
                                opening_total = curr

        cursor.execute('''
            INSERT INTO market_odds
                (game_id, home_team, away_team, spread_home, total_over,
                 opening_spread_home, opening_total, commence_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                spread_home   = excluded.spread_home,
                total_over    = excluded.total_over,
                commence_time = excluded.commence_time,
                last_updated  = CURRENT_TIMESTAMP
        ''', (game_id, home_team, away_team, spread_home, total_over,
              opening_spread, opening_total, commence))
        inserted += 1

    conn.commit()
    return inserted

# ─── Analysis pipeline ────────────────────────────────────────────────────────

def run_analysis(conn, notifier: TelegramNotifier) -> int:
    """Evaluate all current market odds and send BET alerts. Returns count of BETs."""
    cursor   = conn.cursor()
    engine   = BetDecisionEngine(conn)
    bets_sent = 0

    cursor.execute('''
        SELECT game_id, home_team, away_team, spread_home, total_over, commence_time
        FROM market_odds
    ''')
    games = cursor.fetchall()

    for game in games:
        game_id, home_name, away_name, spread_home, total_over, commence = game

        cursor.execute('''
            SELECT m.bdl_team_id, t.is_mid_major
            FROM team_mapping m
            JOIN team_stats t ON m.bdl_team_id = t.team_id
            WHERE m.odds_team_name = ?
        ''', (home_name,))
        home_row = cursor.fetchone()

        cursor.execute('''
            SELECT m.bdl_team_id, t.is_mid_major
            FROM team_mapping m
            JOIN team_stats t ON m.bdl_team_id = t.team_id
            WHERE m.odds_team_name = ?
        ''', (away_name,))
        away_row = cursor.fetchone()

        if not home_row or not away_row:
            continue

        game_data = {
            "game_id":          game_id,
            "home_team":        home_name,
            "away_team":        away_name,
            "home_team_id":     home_row[0],
            "away_team_id":     away_row[0],
            "home_is_mid_major": bool(home_row[1]),
            "away_is_mid_major": bool(away_row[1]),
            "spread_home":      spread_home,
            "total_over":       total_over,
        }

        result = engine.evaluate_game(game_data)
        if not result:
            continue

        # Log every result to DB
        cursor.execute('''
            INSERT INTO recommendations
                (game_id, date, matchup, pick, line, projected_line, confidence, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result['game_id'], datetime.now().strftime('%Y-%m-%d'),
            result['matchup'], result['recommendation'],
            spread_home, result['projections']['projected_spread'],
            result['confidence'], result['reasons']
        ))

        # BET → Telegram alert only
        if result['recommendation'] == 'BET':
            notifier.send_bet_alert(
                game_id       = result['game_id'],
                matchup       = result['matchup'],
                commence_time = commence,
                market_spread = spread_home,
                proj_spread   = result['projections']['projected_spread'],
                market_total  = total_over,
                proj_total    = result['projections']['projected_total'],
                confidence    = result['confidence'],
                reasons       = result['reasons'],
                signals       = result['signals'],
                conn          = conn
            )
            bets_sent += 1

    conn.commit()
    return bets_sent

# ─── Entry point ──────────────────────────────────────────────────────────────

def get_season_record(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT outcome FROM recommendations WHERE outcome IS NOT NULL")
    rows   = cursor.fetchall()
    wins   = sum(1 for r in rows if r[0] and r[0].upper() == 'WIN')
    losses = sum(1 for r in rows if r[0] and r[0].upper() == 'LOSS')
    return wins, losses

def main():
    init_db()
    conn     = get_connection()
    notifier = TelegramNotifier()

    slate_size = sync_odds(conn)
    bets_sent  = run_analysis(conn, notifier)

    ats_w, ats_l = get_season_record(conn)
    now = datetime.now().strftime('%I:%M %p')

    notifier.send_status_update(
        last_run     = f"Today {now}",
        picks_today  = bets_sent,
        season_ats_w = ats_w,
        season_ats_l = ats_l,
        next_run     = "Scheduled (see scheduler)"
    )

    conn.close()
    print(f"Run complete — slate: {slate_size} games | BETs: {bets_sent}")

if __name__ == "__main__":
    main()
