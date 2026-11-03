"""openplay: open men's soccer event data with xG on every shot."""

from ._data import cache_dir, clear_cache, set_data_dir, DATA_REPO, DATA_TAG
from .api import (
    CoverageWarning,
    PlayerWarning,
    cards,
    competitions,
    coverage_report,
    data_issues,
    events,
    formations,
    known_gaps,
    lineups,
    matches,
    name_key,
    normalize_season,
    player_career,
    player_match_stats,
    player_season_stats,
    players,
    shots,
    suggest_players,
    team_match_stats,
    teams,
)

__version__ = "0.1.0"

__all__ = [
    "CoverageWarning", "PlayerWarning", "name_key", "player_career", "suggest_players", "cache_dir", "cards", "clear_cache", "competitions", "coverage_report", "data_issues", "events",
    "formations", "known_gaps", "lineups", "matches", "normalize_season", "player_match_stats", "player_season_stats", "players", "set_data_dir",
    "shots", "team_match_stats", "teams", "DATA_REPO", "DATA_TAG", "__version__",
]
