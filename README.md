# openplay (Python)

Read the [openplay](https://github.com/nlbair/openplay) soccer event data in Python. It covers 26,536 men's matches with every pass, shot and tackle, plus xG on every shot. Files download once from the data release, are checked against published SHA-256 checksums, and are cached on your computer.

The R package [openplay-r](https://github.com/nlbair/openplay-r) has the same functions and returns the same numbers.

## Install

```bash
pip install git+https://github.com/nlbair/openplay-py
```

## Use

```python
import openplay as op

op.competitions()
m = op.matches("eng", "2024/25")
e = op.events("eng", "2024/25", columns=["match_id", "type", "x", "y", "player"])
s = op.shots("eng", "2024/25")
p = op.player_match_stats("eng", "2024/25")
ps = op.player_season_stats("eng", "2024/25", per90=True, min_minutes=900)
op.player_season_stats("esp", "2016/17", player="Cristiano Ronaldo")
op.player_career("Lionel Messi")
t = op.team_match_stats("eng", "2024/25")
op.lineups("ucl", "2425")
op.players()
op.teams()
op.coverage_report("nla")
op.known_gaps()
op.data_issues()
```

- **Seasons.** You can write a season as `"2024/25"`, `"2024-25"` or `"2425"`. Tournaments use the year, for example `"2022"`.
- **Players.** `player=` takes the full name. Capitals and accents don't matter (`"kylian mbappe"` works). A misspelling gets a warning like *No player named 'Lionel Messsi'. Did you mean: Lionel Messi?* If two players share a name, use `player_id=`. The functions that take `player=` are `player_season_stats`, `player_match_stats`, `player_career`, `shots`, `lineups` and `events`.
- **Gaps.** When a request includes matches that have no event data, or have a known data issue, you get a `CoverageWarning`. It never stops your code with an error.
- **Local copy.** If you already have the files on disk, `op.set_data_dir(path)` reads them from there. Setting the `OPENPLAY_DATA_DIR` environment variable does the same.
- **Cache.** Downloads are kept in `op.cache_dir()`. `op.clear_cache()` frees the space.

## Functions

| Function | Returns |
|---|---|
| `competitions()` | one row per competition |
| `matches(comp, season)` | one row per match |
| `events(comp, season, columns)` | one row per event (`comp` is required) |
| `shots(comp, season)` | one row per shot, with xG and the player who set it up |
| `lineups(comp, season)` | one row per player in each matchday squad |
| `player_match_stats(comp, season)` | one row per player per match played, about 80 counts |
| `player_season_stats(comp, season, per90, min_minutes, player)` | season totals or per-90 numbers per player and team |
| `player_career(player, per90)` | one player's whole career: one row per competition, season and team |
| `suggest_players(name)` | the closest full names to what was typed |
| `team_match_stats(comp, season)` | one row per team per match |
| `players()`, `teams()` | one row per player or team |
| `formations(comp, season)`, `cards(comp, season)` | formation spells and cards |
| `coverage_report(comp, season)`, `known_gaps()`, `data_issues()` | what's covered and what's missing |

## Tests

The tests run on a small sample dataset (every UEFA Super Cup plus Nations League A 2022/23), with no download needed:

```bash
python -m unittest discover -s tests
```

## License

Code: MIT. Data: CC-BY 4.0; credit "openplay (Noah Bair)".
