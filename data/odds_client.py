import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.utils import get_retry_session
from alerts.telegram import TelegramNotifier

class OddsAPIClient:
    def __init__(self):
        self.api_key = os.environ.get('ODDS_API_KEY')
        self.base_url = "https://api.the-odds-api.com/v4/sports"
        self.session = get_retry_session()
        self.notifier = TelegramNotifier()

    def get_cbb_odds(self, regions='us', markets='h2h,spreads,totals'):
        url = f"{self.base_url}/basketball_ncaab/odds/"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "american"
        }
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Odds API Error: {e}")
            self.notifier.send_error_alert()
            return []
