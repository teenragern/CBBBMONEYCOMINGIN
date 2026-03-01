import pandas as pd
import numpy as np

class EfficiencyEngine:
    """
    Calculates adjusted offensive/defensive efficiency and pace for each team
    using the possession formula: FGA + 0.475 * FTA - ORB + TOV
    """

    MIN_GAMES = 5  # minimum game sample before projecting

    def __init__(self, conn):
        self.conn = conn

    def calculate_efficiency(self, team_id):
        query = "SELECT * FROM team_game_logs WHERE team_id = ?"
        df = pd.read_sql_query(query, self.conn, params=(team_id,))

        if df.empty or len(df) < self.MIN_GAMES:
            return None  # not enough data

        df['game_date'] = pd.to_datetime(df['game_date'])
        df = df.sort_values('game_date', ascending=False)

        def compute_metrics(subset):
            if subset.empty or subset['possessions'].sum() == 0:
                return 0, 0, 0
            off_eff = (subset['points_scored'].sum() / subset['possessions'].sum()) * 100
            def_eff = (subset['points_allowed'].sum() / subset['possessions'].sum()) * 100
            pace = subset['possessions'].mean()
            return off_eff, def_eff, pace

        full_off, full_def, full_pace = compute_metrics(df)
        if full_off == 0:
            return None

        recent_df = df.head(5)
        recent_off, recent_def, recent_pace = compute_metrics(recent_df)

        # 60% recent, 40% full-season weighting
        final_off =  (recent_off  * 0.6) + (full_off  * 0.4)
        final_def =  (recent_def  * 0.6) + (full_def  * 0.4)
        final_pace = (recent_pace * 0.6) + (full_pace * 0.4)

        return {"off_eff": final_off, "def_eff": final_def, "pace": final_pace}

    def project_matchup(self, home_team_id, away_team_id):
        home = self.calculate_efficiency(home_team_id)
        away = self.calculate_efficiency(away_team_id)

        if not home or not away:
            return None

        avg_pace = (home['pace'] + away['pace']) / 2

        home_eff = (home['off_eff'] + away['def_eff']) / 2
        away_eff = (away['off_eff'] + home['def_eff']) / 2

        home_score = (home_eff * avg_pace) / 100 + 1.5  # HCA adjustment
        away_score = (away_eff * avg_pace) / 100 - 1.5

        return {
            "home_score": home_score,
            "away_score": away_score,
            "projected_spread": away_score - home_score,
            "projected_total": home_score + away_score
        }
