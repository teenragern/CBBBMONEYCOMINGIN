import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.utils import get_retry_session
from alerts.telegram import TelegramNotifier

class BallDontLieClient:
    def __init__(self):
        self.api_key = os.environ.get('BDL_API_KEY')
        self.base_url = "https://api.balldontlie.io/ncaab/v1"
        self.headers = {"Authorization": self.api_key}
        self.session = get_retry_session()
        self.notifier = TelegramNotifier()

    def _get(self, endpoint, params=None):
        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint}",
                headers=self.headers,
                params=params,
                timeout=15
            )
            response.raise_for_status()
            return response.json().get('data', [])
        except Exception as e:
            print(f"BDL API Error ({endpoint}): {e}")
            self.notifier.send_error_alert()
            return []

    def get_teams(self):
        return self._get("teams")

    def get_game_logs(self, team_id, season=2024):
        return self._get("games", {"seasons[]": season, "team_ids[]": team_id})

    def get_box_score_stats(self, game_id):
        return self._get("stats", {"game_ids[]": game_id})
