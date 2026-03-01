class LineMovementTracker:
    """
    Tracks line movement between opening and current lines.
    Flags games where the spread or total moved >= 2 points (sharp money signal).
    """

    def __init__(self, conn):
        self.conn = conn

    def get_sharp_signal(self, game_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT spread_home, opening_spread_home, total_over, opening_total
            FROM market_odds WHERE game_id = ?
        ''', (game_id,))
        row = cursor.fetchone()

        if not row:
            return False, 0, 0

        curr_spread, open_spread, curr_total, open_total = row

        spread_move = abs(curr_spread - open_spread) if (curr_spread is not None and open_spread is not None) else 0
        total_move  = abs(curr_total  - open_total)  if (curr_total  is not None and open_total  is not None) else 0

        is_sharp = spread_move >= 2 or total_move >= 2
        return is_sharp, spread_move, total_move
