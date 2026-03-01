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

        # Line Shopping and Average Market Data unpack
        best_spread_home = game_data.get('spread_home')
        best_spread_away = game_data.get('spread_away')
        best_total_over  = game_data.get('total_over')
        best_total_under = game_data.get('total_under')
        
        market_avg_spread = game_data.get('market_avg_spread')
        market_avg_total  = game_data.get('market_avg_total')

        is_sharp, spread_move, total_move = self.line_tracker.get_sharp_signal(game_id)

        conditions_met = 0
        reasons = []

        # 1. Spread edge >= 2 pts (compare against best available line now)
        proj_home_spread = projections.get('projected_spread')
        proj_away_spread = -proj_home_spread if proj_home_spread is not None else None
        
        spread_diff = 0
        target_spread = None
        target_spread_side = None
        target_bookie = None
        
        if proj_home_spread is not None and best_spread_home is not None and best_spread_away is not None:
            home_diff = proj_home_spread - best_spread_home # e.g. -6 projected vs -4 available = -2
            away_diff = proj_away_spread - best_spread_away
            
            # Since taking points limits (- values), the math gets slightly tricky.
            # Simplified for Edge calculation absolute differences:
            home_edge = (best_spread_home - proj_home_spread) # -4 - (-6) = +2 edge
            away_edge = (best_spread_away - proj_away_spread)
            
            if home_edge >= 2:
                conditions_met += 1
                spread_diff = home_edge
                target_spread = best_spread_home
                target_spread_side = "Home"
                target_bookie = game_data.get('spread_home_bookmaker')
                reasons.append(f"Spread edge ({home_edge:.1f} pts on Home)")
            elif away_edge >= 2:
                conditions_met += 1
                spread_diff = away_edge
                target_spread = best_spread_away
                target_spread_side = "Away"
                target_bookie = game_data.get('spread_away_bookmaker')
                reasons.append(f"Spread edge ({away_edge:.1f} pts on Away)")

        # 2. Total edge >= 3 pts
        total_diff = 0
        target_total = None
        target_total_side = None
        target_total_bookie = None
        
        proj_total = projections.get('projected_total')
        if proj_total is not None and best_total_over is not None and best_total_under is not None:
            over_edge = proj_total - best_total_over
            under_edge = best_total_under - proj_total
            
            if over_edge >= 3:
                conditions_met += 1
                total_diff = over_edge
                target_total = best_total_over
                target_total_side = "Over"
                target_total_bookie = game_data.get('total_over_bookmaker')
                reasons.append(f"Total edge ({over_edge:.1f} pts on Over)")
            elif under_edge >= 3:
                conditions_met += 1
                total_diff = under_edge
                target_total = best_total_under
                target_total_side = "Under"
                target_total_bookie = game_data.get('total_under_bookmaker')
                reasons.append(f"Total edge ({under_edge:.1f} pts on Under)")

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
        signals_count  = conditions_met
        
        # Calculate Kelly Fraction 
        from models.bankroll import extract_win_prob, calculate_kelly_fraction
        
        # we pass highest edge found between Spread/Total for simple sizing
        max_edge = max(spread_diff, total_diff)
        true_prob = extract_win_prob(confidence, signals_count, max_edge)
        recommended_wager_pct = calculate_kelly_fraction(true_prob, odds=-110) * 100 # percentage formatting

        return {
            "game_id":        game_id,
            "matchup":        f"{game_data['away_team']} @ {game_data['home_team']}",
            "recommendation": recommendation,
            "confidence":     confidence,
            "signals":        signals_count,
            "projections":    projections,
            "reasons":        "; ".join(reasons) if reasons else "No clear edge",
            
            # Line Shopping Payload Additions
            "target_spread": target_spread,
            "target_spread_side": target_spread_side,
            "target_spread_bookie": target_bookie,
            "market_avg_spread": market_avg_spread,
            
            "target_total": target_total,
            "target_total_side": target_total_side,
            "target_total_bookie": target_total_bookie,
            "market_avg_total": market_avg_total,
            
            # Wager sizing
            "wager_pct": recommended_wager_pct,
            "highest_edge": max_edge
        }
