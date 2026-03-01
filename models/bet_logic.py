from models.efficiency import EfficiencyEngine
from models.line_movement import LineMovementTracker

class BetDecisionEngine:
    """
    Core BET/PASS decision layer.
    Scores each game against 4 conditions; BET if >= 2 conditions met.
    """

    def __init__(self, conn):
        self.conn = conn
        self.efficiency = EfficiencyEngine(conn)
        self.line_tracker = LineMovementTracker(conn)

    def evaluate_game(self, game_data):
        game_id      = game_data['game_id']
        home_team_id = game_data['home_team_id']
        away_team_id = game_data['away_team_id']

        projections = self.efficiency.project_matchup(home_team_id, away_team_id)
        if not projections:
            return None

        market_spread = game_data.get('spread_home')
        market_total  = game_data.get('total_over')
        is_sharp, spread_move, total_move = self.line_tracker.get_sharp_signal(game_id)

        conditions_met = 0
        reasons = []

        # 1. Spread edge >= 2 pts
        if market_spread is not None and projections.get('projected_spread') is not None:
            spread_diff = abs(projections['projected_spread'] - market_spread)
            if spread_diff >= 2:
                conditions_met += 1
                reasons.append(f"Spread edge ({spread_diff:.1f} pts)")

        # 2. Total edge >= 3 pts
        if market_total is not None and projections.get('projected_total') is not None:
            total_diff = abs(projections['projected_total'] - market_total)
            if total_diff >= 3:
                conditions_met += 1
                reasons.append(f"Total edge ({total_diff:.1f} pts)")

        # 3. Sharp line movement
        if is_sharp:
            conditions_met += 1
            reasons.append(f"Sharp movement (spread {spread_move:.1f} / total {total_move:.1f} pts)")

        # 4. Mid-major priority
        if game_data.get('home_is_mid_major') or game_data.get('away_is_mid_major'):
            conditions_met += 1
            reasons.append("Mid-major game priority")

        recommendation = "BET"  if conditions_met >= 2 else "PASS"
        confidence     = "HIGH" if conditions_met >= 3 else ("MEDIUM" if conditions_met == 2 else "LOW")

        signals_count = conditions_met

        return {
            "game_id":        game_id,
            "matchup":        f"{game_data['away_team']} @ {game_data['home_team']}",
            "recommendation": recommendation,
            "confidence":     confidence,
            "signals":        signals_count,
            "projections":    projections,
            "reasons":        "; ".join(reasons) if reasons else "No clear edge"
        }
