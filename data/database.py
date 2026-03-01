import sqlite3
import os

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'cbb_bot.db'))

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_stats (
            team_id INTEGER PRIMARY KEY,
            team_name TEXT,
            conference TEXT,
            is_mid_major INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_game_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER,
            team_id INTEGER,
            points_scored REAL,
            points_allowed REAL,
            possessions REAL,
            game_date TEXT,
            is_home INTEGER,
            UNIQUE(game_id, team_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_mapping (
            odds_team_name TEXT PRIMARY KEY,
            bdl_team_id INTEGER,
            confidence REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_odds (
            game_id TEXT PRIMARY KEY,
            home_team TEXT,
            away_team TEXT,
            spread_home REAL,
            spread_home_bookmaker TEXT,
            spread_away REAL,
            spread_away_bookmaker TEXT,
            total_over REAL,
            total_over_bookmaker TEXT,
            total_under REAL,
            total_under_bookmaker TEXT,
            market_avg_spread REAL,
            market_avg_total REAL,
            commence_time TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT,
            date TEXT,
            matchup TEXT,
            pick TEXT,
            line REAL,
            projected_line REAL,
            confidence TEXT,
            reasoning TEXT,
            units_wagered REAL,
            units_won REAL,
            outcome TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_status (
            key TEXT PRIMARY KEY,
            value TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Initialize circuit breaker to ACTIVE
    cursor.execute('''
        INSERT OR IGNORE INTO system_status (key, value) VALUES ('stop_loss_triggered', 'False')
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notified_games (
            game_id TEXT,
            notification_date DATE,
            PRIMARY KEY (game_id, notification_date)
        )
    ''')

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")
