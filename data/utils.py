import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def get_retry_session(retries=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]):
    """Creates a requests session with automatic retry logic on failures."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_espn_injuries():
    """
    Fetches real-time injury data from ESPN's free Men's CBB injuries endpoint.
    Returns a dict mapping team names to lists of injured players.
    """
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/injuries"
    session = get_retry_session()
    injuries_map = {}
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for team_data in data.get('injuries', []):
            team_name = team_data.get('team', {}).get('displayName')
            if not team_name:
                continue
            team_injuries = []
            for inj in team_data.get('injuries', []):
                athlete = inj.get('athlete', {}).get('displayName', 'Unknown')
                status = inj.get('status', 'Unknown')
                if status.lower() not in ['active', 'probable']:
                    team_injuries.append(f"{athlete} ({status})")
            if team_injuries:
                injuries_map[team_name] = team_injuries
    except Exception as e:
        print(f"ESPN injury fetch error: {e}")
    return injuries_map
