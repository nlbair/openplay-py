import re
import unicodedata
import warnings

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import _data


class CoverageWarning(UserWarning):
    """Raised as a warning when a request touches matches with no event data."""


class PlayerWarning(UserWarning):
    """Raised as a warning when a player name has no exact match or matches several players."""


_FOLD = str.maketrans({"\u00f8": "o", "\u00d8": "O", "\u0142": "l", "\u0141": "L", "\u0111": "d", "\u0110": "D", "\u00df": "ss",
                       "\u00e6": "ae", "\u00c6": "AE", "\u0153": "oe", "\u0152": "OE", "\u0131": "i", "\u00fe": "th", "\u00de": "TH",
                       "\u00f0": "d", "\u00d0": "D", "\u0127": "h", "\u0126": "H", "\u2019": "'", "\u2018": "'"})


def name_key(name):
    """Lower-case a name and strip accents, so 'Kylian Mbapp\u00e9' and 'kylian mbappe' match."""
    s = unicodedata.normalize("NFKD", str(name).translate(_FOLD))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().lower()


def _edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _player_keys():
    pl = players()[["player_id", "player"]].dropna()
    return pl.assign(key=pl["player"].astype(str).map(name_key))


def suggest_players(name, n=5):
    """Full names closest to ``name``: small spelling mistakes, or names that contain every word typed."""
    key = name_key(name)
    pl = _player_keys().drop_duplicates("key")
    limit = max(2, len(key) // 4)
    words = set(key.split())
    hits = []
    for k, full in zip(pl["key"], pl["player"]):
        partial = bool(words) and words <= set(k.split())
        if partial or abs(len(k) - len(key)) <= limit:
            d = _edit_distance(key, k)
            if partial or d <= limit:
                hits.append((0 if partial else 1, d, k, str(full)))
    hits.sort()
    return [h[3] for h in hits[:n]]


def _player_ids(player, player_id):
    if player_id is not None:
        return {int(x) for x in _as_list(player_id)}
    if player is None:
        return None
    pl = _player_keys()
    ids = set()
    for name in _as_list(player):
        found = pl[pl["key"] == name_key(name)]
        if found.empty:
            sug = suggest_players(name)
            if sug:
                msg = f"No player named '{name}'. Did you mean: " + ", ".join(sug) + "?"
            else:
                msg = f"No player named '{name}'. Check the spelling (use the full name) or search players()."
            warnings.warn(msg, PlayerWarning, stacklevel=3)
            continue
        found_ids = sorted(int(i) for i in found["player_id"].unique())
        if len(found_ids) > 1:
            warnings.warn(f"{len(found_ids)} players are named '{name}' (player_id " + ", ".join(str(i) for i in found_ids) + "); all are included. Use player_id= to pick one.", PlayerWarning, stacklevel=3)
        ids |= set(found_ids)
    return ids


def _keep_players(df, ids, col="player_id"):
    if ids is None:
        return df
    out = df[df[col].isin(ids)].reset_index(drop=True)
    if ids and out.empty:
        pl = players()
        names = ", ".join(f"{n} (player_id {int(i)})" for i, n in zip(pl["player_id"], pl["player"]) if int(i) in ids)
        warnings.warn(f"Found {names}, but there are no rows for them in this selection (they may not have played in this competition or season); try player_career().", PlayerWarning, stacklevel=3)
    return out


def _as_list(x):
    if x is None:
        return None
    if isinstance(x, (list, tuple, set, pd.Series)):
        return [str(v) for v in x]
    return [str(x)]


def normalize_season(season):
    """Turn '2024/25', '2024-25', '2024/2025' or '2425' into the stored form '2425'.

    Tournament years such as '2022' are returned unchanged.
    """
    s = str(season).strip()
    m = re.fullmatch(r"(\d{4})\s*[/-]\s*(\d{2}|\d{4})", s)
    if m:
        return m.group(1)[2:] + m.group(2)[-2:]
    return s


def _seasons(season):
    v = _as_list(season)
    return None if v is None else [normalize_season(x) for x in v]


def _read_table(name, comp=None, season=None, columns=None):
    df = pd.read_parquet(_data.fetch(name + ".parquet"), columns=columns)
    comps, seasons = _as_list(comp), _seasons(season)
    if comps is not None and "comp" in df.columns:
        df = df[df["comp"].astype(str).isin(comps)]
    if seasons is not None and "season" in df.columns:
        df = df[df["season"].astype(str).isin(seasons)]
    return df.reset_index(drop=True)


def competitions():
    """All competitions with their names, type, seasons and whether they are in the v1 scope."""
    return _read_table("competitions")


def coverage_report(comp=None, season=None, warn=True):
    """Matches played, matches with event data, and known gaps per competition-season.

    Never raises for gaps. With ``warn=True`` it issues a ``CoverageWarning``
    when the selection includes matches that have no event data or have a
    known data issue.
    """
    cov = pd.read_csv(_data.fetch("coverage.csv"), dtype={"season": str})
    comps, seasons = _as_list(comp), _seasons(season)
    if comps is not None:
        cov = cov[cov["comp"].isin(comps)]
    if seasons is not None:
        cov = cov[cov["season"].isin(seasons)]
    cov = cov.reset_index(drop=True)
    if warn and len(cov):
        gaps = int(cov["gaps"].sum())
        issues = int(cov["matches_with_data_issues"].sum())
        if gaps:
            warnings.warn(f"{gaps} played match(es) in this selection have no event data; see known_gaps()", CoverageWarning, stacklevel=2)
        if issues:
            warnings.warn(f"{issues} match(es) in this selection have known data issues; see data_issues()", CoverageWarning, stacklevel=2)
    return cov


def _check(comp, season, ids=None):
    if ids is not None and not ids:
        return
    try:
        coverage_report(comp, season, warn=True)
    except Exception:
        pass


def known_gaps(comp=None, season=None):
    """Played matches that have no event data, with date, teams and score where known."""
    df = pd.read_csv(_data.fetch("known_gaps.csv"), dtype={"season": str})
    comps, seasons = _as_list(comp), _seasons(season)
    if comps is not None:
        df = df[df["comp"].isin(comps)]
    if seasons is not None:
        df = df[df["season"].isin(seasons)]
    return df.reset_index(drop=True)


def data_issues(comp=None, season=None):
    """Matches whose events are partial, whose lineups are incomplete, or whose events disagree with the official score."""
    df = pd.read_csv(_data.fetch("data_issues.csv"), dtype={"season": str})
    comps, seasons = _as_list(comp), _seasons(season)
    if comps is not None:
        df = df[df["comp"].isin(comps)]
    if seasons is not None:
        df = df[df["season"].isin(seasons)]
    return df.reset_index(drop=True)


def matches(comp=None, season=None, in_scope_only=False):
    """One row per match with teams, scores, venue, referee, managers and formations."""
    df = _read_table("matches", comp, season)
    if in_scope_only:
        df = df[df["in_v1_scope"]].reset_index(drop=True)
    _check(comp, season)
    return df


def events(comp, season=None, columns=None, player=None, player_id=None):
    """Every event for one or more competition-seasons.

    ``comp`` is required because the full dataset has about 42 million rows.
    ``season`` may be one season, a list, or ``None`` for every season of the
    competition. ``columns`` limits the columns read, which saves memory.
    ``player`` keeps one player's events (full name; capitals and accents are ignored).
    """
    ids = _player_ids(player, player_id)
    if ids is not None and columns is not None and "player_id" not in columns:
        columns = list(columns) + ["player_id"]
    comps = _as_list(comp)
    if not comps:
        raise ValueError("events() needs at least one competition code, for example events('eng', '2425')")
    seasons = _seasons(season)
    names = []
    for f in _data.available_files():
        m = re.fullmatch(r"events_([a-z]+)_(\d+)\.parquet", f)
        if m and m.group(1) in comps and (seasons is None or m.group(2) in seasons):
            names.append(f)
    if not names:
        raise ValueError(f"no event files for comp={comps} season={seasons}; see competitions() for what exists")
    frames = []
    for n in sorted(names):
        path = _data.fetch(n)
        cols = None
        if columns is not None:
            have = set(pq.read_schema(path).names)
            cols = [c for c in columns if c in have]
        frames.append(_keep_players(pd.read_parquet(path, columns=cols), ids))
    _check(comp, season, ids)
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True, sort=False)


def shots(comp=None, season=None, player=None, player_id=None):
    """Every shot with location, body part, situation, outcome, xG and the player who set it up.

    ``player`` keeps one player's shots (full name; capitals and accents are ignored).
    """
    ids = _player_ids(player, player_id)
    df = _keep_players(_read_table("shots", comp, season), ids)
    _check(comp, season, ids)
    return df


def lineups(comp=None, season=None, player=None, player_id=None):
    """Every player in every matchday squad: starter or sub, minutes, position.

    ``player`` keeps one player's rows (full name; capitals and accents are ignored).
    """
    ids = _player_ids(player, player_id)
    df = _keep_players(_read_table("lineups", comp, season), ids)
    _check(comp, season, ids)
    return df


def player_match_stats(comp=None, season=None, player=None, player_id=None):
    """One row per player per match played, with about 80 counts built from the events.

    ``player`` keeps one player's matches (full name; capitals and accents are ignored).
    """
    ids = _player_ids(player, player_id)
    df = _keep_players(_read_table("player_match_stats", comp, season), ids)
    _check(comp, season, ids)
    return df


def team_match_stats(comp=None, season=None):
    """One row per team per match, with the same counts plus goals, xG and shots against."""
    df = _read_table("team_match_stats", comp, season)
    _check(comp, season)
    return df


def players():
    """One row per player: name, height, weight, estimated birth year, main position, appearances and minutes."""
    return _read_table("players")


def teams():
    """One row per team: name, country, club or national team, and competitions played."""
    return _read_table("teams")


def formations(comp=None, season=None):
    """Every formation a team used in a match, with the minutes it was used."""
    df = _read_table("formations")
    if comp is not None or season is not None:
        ids = matches(comp, season)["match_id"]
        df = df[df["match_id"].isin(ids)].reset_index(drop=True)
    return df


def cards(comp=None, season=None):
    """Every card shown, with player, team and minute."""
    df = _read_table("cards")
    if comp is not None or season is not None:
        ids = matches(comp, season)["match_id"]
        df = df[df["match_id"].isin(ids)].reset_index(drop=True)
    return df


_ID_COLS = ["comp", "season", "player_id", "player", "team_id", "team"]
_NOT_SUMMED = {"match_id", "date", "opponent_id", "opponent", "side", "position", "is_starter", "played", "in_lineup", "minute_on", "minute_off", "pass_pct"}


def player_season_stats(comp=None, season=None, per90=False, min_minutes=0, player=None, player_id=None):
    """Season totals per player and team, built from player_match_stats.

    A player who moved clubs mid-season gets one row per team. With
    ``per90=True`` every count is divided by minutes played and multiplied by
    90. ``min_minutes`` drops rows below that many minutes. ``player`` keeps
    one player (full name; capitals and accents are ignored).
    """
    ids = _player_ids(player, player_id)
    p = player_match_stats(comp, season, player_id=None if ids is None else sorted(ids))
    p = p.assign(comp=p["comp"].astype(str), season=p["season"].astype(str))
    p = p.sort_values(["comp", "season", "player_id", "team_id", "date", "match_id"], kind="mergesort")
    p["is_starter"] = p["is_starter"].fillna(False).astype(bool)
    counts = [c for c in p.columns if c not in _ID_COLS and c not in _NOT_SUMMED and c != "minutes_played" and pd.api.types.is_numeric_dtype(p[c])]
    p[counts] = p[counts].astype("float64")
    g = p.groupby(["comp", "season", "player_id", "team_id"], sort=True)
    out = g[counts].sum()
    out.insert(0, "minutes_played", g["minutes_played"].sum())
    out.insert(0, "starts", g["is_starter"].sum().astype("int64"))
    out.insert(0, "matches", g["match_id"].nunique())
    out.insert(0, "team", g["team"].last())
    out.insert(0, "player", g["player"].last())
    out = out.reset_index()
    out["pass_pct"] = np.floor(1000 * out["passes_completed"] / out["passes"].where(out["passes"] > 0) + 0.5) / 10
    out["minutes_played"] = out["minutes_played"].astype("float64")
    out = out[out["minutes_played"] >= min_minutes].reset_index(drop=True)
    if per90:
        mins = out["minutes_played"].where(out["minutes_played"] > 0)
        for c in counts:
            out[c] = out[c].astype("float64") / mins * 90
    for c in counts:
        if not per90 and c not in ("xg", "npxg", "xa"):
            out[c] = out[c].astype("int64")
        else:
            out[c] = out[c].astype("float64")
    return out


def player_career(player=None, player_id=None, per90=False):
    """One player's whole career in the data: one row per competition, season and team, oldest first.

    ``player`` is the full name (capitals and accents are ignored). A close
    misspelling gets a "did you mean" warning and an empty result.
    """
    if player is None and player_id is None:
        raise ValueError("player_career() needs a full player name or a player_id, for example player_career('Lionel Messi')")
    ids = _player_ids(player, player_id)
    if not ids:
        return pd.DataFrame(columns=["player_id", "player", "comp", "season", "team_id", "team", "first_match"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CoverageWarning)
        out = player_season_stats(per90=per90, player_id=sorted(ids))
        pm = player_match_stats(player_id=sorted(ids))
    pm = pm.assign(comp=pm["comp"].astype(str), season=pm["season"].astype(str))
    first = pm.groupby(["comp", "season", "player_id", "team_id"])["date"].min().rename("first_match").reset_index()
    out = out.merge(first, on=["comp", "season", "player_id", "team_id"], how="left")
    out = out.sort_values(["player_id", "first_match", "comp", "team_id"], kind="mergesort").reset_index(drop=True)
    cov = coverage_report(warn=False)
    pairs = set(zip(out["comp"], out["season"]))
    cov = cov[[(c, x) in pairs for c, x in zip(cov["comp"], cov["season"])]]
    if int(cov["gaps"].sum()):
        warnings.warn(f"{int(cov['gaps'].sum())} played match(es) in this player's competition-seasons have no event data, so the totals may miss some of their matches; see known_gaps()", CoverageWarning, stacklevel=2)
    cols = ["player_id", "player", "comp", "season", "team_id", "team", "first_match"]
    return out[cols + [c for c in out.columns if c not in cols]]
