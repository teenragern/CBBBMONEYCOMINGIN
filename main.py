import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import pytz

EST = pytz.timezone('US/Eastern')

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

        # Bookie Tracking
        spreads_home = []
        spreads_away = []
        totals_over  = []
        totals_under = []

        for bm in g.get('bookmakers', []):
            book_name = bm.get('title', 'Unknown')
            for mkt in bm.get('markets', []):
                if mkt['key'] == 'spreads':
                    for outcome in mkt.get('outcomes', []):
                        point = outcome.get('point')
                        if point is None: continue
                        if outcome['name'] == home_team:
                            spreads_home.append((point, book_name))
                        else:
                            spreads_away.append((point, book_name))
                elif mkt['key'] == 'totals':
                    for outcome in mkt.get('outcomes', []):
                        point = outcome.get('point')
                        if point is None: continue
                        if outcome['name'] == 'Over':
                            totals_over.append((point, book_name))
                        else:
                            totals_under.append((point, book_name))

        if not spreads_home or not totals_over:
            continue

        # Best Odds Calculation (You want highest number for spread/total)
        # Note: -3 is better than -4. +5 is better than +4. The mathematical maximum is the best.
        best_home = max(spreads_home, key=lambda x: x[0])
        best_away = max(spreads_away, key=lambda x: x[0])
        
        # Best totals mathematically (lowest over is best, highest under is best)
        best_over  = min(totals_over, key=lambda x: x[0])
        best_under = max(totals_under, key=lambda x: x[0])
        
        avg_spread = sum(x[0] for x in spreads_home) / len(spreads_home)
        avg_total  = sum(x[0] for x in totals_over) / len(totals_over)

        cursor.execute('''
            INSERT INTO market_odds
                (game_id, home_team, away_team, 
                 spread_home, spread_home_bookmaker, 
                 spread_away, spread_away_bookmaker,
                 total_over, total_over_bookmaker,
                 total_under, total_under_bookmaker,
                 market_avg_spread, market_avg_total,
                 commence_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                spread_home = excluded.spread_home,
                spread_home_bookmaker = excluded.spread_home_bookmaker,
                spread_away = excluded.spread_away,
                spread_away_bookmaker = excluded.spread_away_bookmaker,
                total_over = excluded.total_over,
                total_over_bookmaker = excluded.total_over_bookmaker,
                total_under = excluded.total_under,
                total_under_bookmaker = excluded.total_under_bookmaker,
                market_avg_spread = excluded.market_avg_spread,
                market_avg_total = excluded.market_avg_total,
                commence_time = excluded.commence_time,
                last_updated = CURRENT_TIMESTAMP
        ''', (
            game_id, home_team, away_team, 
            best_home[0], best_home[1], 
            best_away[0], best_away[1],
            best_over[0], best_over[1], 
            best_under[0], best_under[1],
            avg_spread, avg_total, commence))
        inserted += 1

    conn.commit()
    return inserted

# ─── Analysis pipeline ────────────────────────────────────────────────────────

def run_analysis(conn, notifier: TelegramNotifier) -> int:
    """Evaluate all current market odds and send BET alerts. Returns count of BETs."""
    
    from models.bankroll import check_stop_loss
    is_locked, current_pnl = check_stop_loss(conn)
    if is_locked:
        print(f"SYSTEM HALTED - Stop loss active (Trailing PnL: {current_pnl} units). No alerts will be sent.")
        return 0
    
    cursor   = conn.cursor()
    engine   = BetDecisionEngine(conn)
    bets_sent = 0

    cursor.execute('''
        SELECT game_id, home_team, away_team, 
               spread_home, spread_home_bookmaker, spread_away, spread_away_bookmaker,
               total_over, total_over_bookmaker, total_under, total_under_bookmaker,
               market_avg_spread, market_avg_total, commence_time
        FROM market_odds
    ''')
    games = cursor.fetchall()

    for game in games:
        (game_id, home_name, away_name, 
         spread_h, spread_h_b, spread_a, spread_a_b, 
         total_o, total_o_b, total_u, total_u_b,
         avg_spread, avg_total, commence) = game

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
            
            "spread_home":      spread_h,
            "spread_home_bookmaker": spread_h_b,
            "spread_away":      spread_a,
            "spread_away_bookmaker": spread_a_b,
            
            "total_over":       total_o,
            "total_over_bookmaker": total_o_b,
            "total_under":      total_u,
            "total_under_bookmaker": total_u_b,
            
            "market_avg_spread": avg_spread,
            "market_avg_total": avg_total,
        }

        result = engine.evaluate_game(game_data)
        if not result:
            continue

        # Log every result to DB
        cursor.execute('''
            INSERT INTO recommendations
                (game_id, date, matchup, pick, line, projected_line, confidence, reasoning, units_wagered)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            result['game_id'], datetime.now(EST).strftime('%Y-%m-%d'),
            result['matchup'], result['recommendation'],
            spread_h, result['projections']['projected_spread'],
            result['confidence'], result['reasons'], result.get('wager_pct', 0)
        ))

        # BET → Telegram alert only
        if result['recommendation'] == 'BET':
            notifier.send_bet_alert(
                game_id       = result['game_id'],
                matchup       = result['matchup'],
                commence_time = commence,
                
                # Payload additions
                result        = result,
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
    from dotenv import load_dotenv
    load_dotenv()
    
    init_db()
    conn     = get_connection()
    notifier = TelegramNotifier()

    slate_size = sync_odds(conn)
    bets_sent  = run_analysis(conn, notifier)

    ats_w, ats_l = get_season_record(conn)
    now = datetime.now(EST).strftime('%I:%M %p')

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
