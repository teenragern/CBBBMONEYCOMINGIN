import sqlite3
import datetime

# ─── Configuration ────────────────────────────────────────────────────────────

MAX_BET_PERCENTAGE = 0.05  # 5% max bet cap
KELLY_FRACTION = 0.5       # Half-Kelly approach for safer bankroll management
STOP_LOSS_THRESHOLD = -10.0 # Shutdown the bot if trailing 7-day PnL hits -10 units

# ─── Bankroll Math ────────────────────────────────────────────────────────────

def calculate_implied_probability(american_odds):
    """Converts American odds (-110, +120) to implied win probability."""
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    else:
        return 100 / (american_odds + 100)

def extract_win_prob(confidence, signals, spread_edge):
    """
    Estimates a true win probability based on bot confidence and edge.
    This is highly theoretical but necessary for Kelly math.
    Base probability starts near 50%, scales with signals/edge.
    """
    # Base 52.38% (Standard break-even on -110)
    base_prob = 0.5238
    
    # Add scalar for edges
    edge_bonus = (spread_edge * 0.005) # +0.5% true win prob per point of edge over market
    signal_bonus = (signals * 0.005)   # +0.5% true win prob per active sharp signal
    
    true_prob = base_prob + edge_bonus + signal_bonus
    return min(true_prob, 0.75) # Cap theoretical win prob at 75% for safety

def calculate_kelly_fraction(true_prob, odds=-110, multiplier=KELLY_FRACTION):
    """
    Calculates the Kelly Criterion fraction to wager.
    Formula: f = (bp - q) / b
    Where:
      b = decimal odds - 1 (profit on $1 wager)
      p = probability of winning
      q = probability of losing (1-p)
    """
    implied_prob = calculate_implied_probability(odds)
    
    # If we don't have an edge, bet nothing.
    if true_prob <= implied_prob:
        return 0.0

    b = (1 / implied_prob) - 1
    p = true_prob
    q = 1.0 - p

    kelly_pct = ((b * p) - q) / b
    
    # Apply Half-Kelly or Quarter-Kelly, and enforce hard max cap
    wager_pct = kelly_pct * multiplier
    return min(wager_pct, MAX_BET_PERCENTAGE)

# ─── Circuit Breaker ──────────────────────────────────────────────────────────

def check_stop_loss(conn):
    """
    Calculates the trailing 7-day PnL from the recommendations table.
    If it breaches the STOP_LOSS_THRESHOLD, triggers the system_status breaker.
    Returns: (is_triggered (bool), current_pnl (float))
    """
    cursor = conn.cursor()
    
    # Check if we're already locked out
    cursor.execute("SELECT value FROM system_status WHERE key = 'stop_loss_triggered'")
    status_row = cursor.fetchone()
    is_locked = status_row and status_row[0] == 'True'

    # Calculate 7-day PnL
    seven_days_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    
    cursor.execute('''
        SELECT SUM(units_won) 
        FROM recommendations 
        WHERE date >= ? AND outcome IS NOT NULL
    ''', (seven_days_ago,))
    
    pnl_row = cursor.fetchone()
    current_pnl = pnl_row[0] if pnl_row and pnl_row[0] is not None else 0.0

    if current_pnl <= STOP_LOSS_THRESHOLD and not is_locked:
        # Trigger breaker
        cursor.execute("UPDATE system_status SET value = 'True' WHERE key = 'stop_loss_triggered'")
        conn.commit()
        return True, current_pnl
        
    return is_locked, current_pnl
