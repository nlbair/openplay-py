import json
import os
import unittest
import warnings
from pathlib import Path

import openplay as op

SAMPLE = Path(os.environ.get("OPENPLAY_SAMPLE_DIR", Path(__file__).parent / "data"))
EXPECTED = json.loads((SAMPLE / "expected.json").read_text())


class SampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        op.set_data_dir(SAMPLE)

    @classmethod
    def tearDownClass(cls):
        op.set_data_dir(None)

    def test_normalize_season(self):
        self.assertEqual(op.normalize_season("2024/25"), "2425")
        self.assertEqual(op.normalize_season("2024-2025"), "2425")
        self.assertEqual(op.normalize_season("2425"), "2425")
        self.assertEqual(op.normalize_season(2022), "2022")

    def test_competitions(self):
        self.assertEqual(len(op.competitions()), EXPECTED["n_competitions"])

    def test_matches(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = op.matches()
        self.assertEqual(len(m), EXPECTED["n_matches"])
        self.assertEqual(int(m["home_score"].sum() + m["away_score"].sum()), EXPECTED["total_goals"])
        self.assertEqual(len(op.matches("usc")), EXPECTED["n_matches_usc"])

    def test_events(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            e = op.events("nla", "2022/23")
        self.assertEqual(len(e), EXPECTED["n_events_nla_2223"])
        self.assertEqual(int((e["type"].astype(str) == "Pass").sum()), EXPECTED["n_passes_nla_2223"])
        small = op.events("usc", columns=["match_id", "type", "xg", "not_a_column"])
        self.assertEqual(list(small.columns), ["match_id", "type", "xg"])

    def test_events_needs_comp(self):
        with self.assertRaises(ValueError):
            op.events(None)

    def test_shots(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = op.shots()
        self.assertEqual(len(s), EXPECTED["n_shots"])
        self.assertAlmostEqual(float(s["xg"].astype("float64").sum()), EXPECTED["sum_xg"], places=3)

    def test_player_stats(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p = op.player_match_stats()
            lu = op.lineups()
        self.assertEqual(len(lu), EXPECTED["n_lineup_rows"])
        self.assertEqual(len(p), EXPECTED["n_player_match_rows"])
        self.assertEqual(int(p["minutes_played"].sum()), EXPECTED["sum_minutes"])
        self.assertEqual(int(p["goals"].sum()), EXPECTED["sum_player_goals"])
        self.assertEqual(int(p["assists"].sum()), EXPECTED["sum_player_assists"])
        self.assertAlmostEqual(float(p["xa"].astype("float64").sum()), EXPECTED["sum_player_xa"], places=3)
        top = p.groupby("player_id")["goals"].sum().reset_index().sort_values(["goals", "player_id"], ascending=[False, True]).iloc[0]
        self.assertEqual(int(top["player_id"]), EXPECTED["top_scorer_player_id"])
        self.assertEqual(int(top["goals"]), EXPECTED["top_scorer_goals"])

    def test_team_stats(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t = op.team_match_stats()
        self.assertEqual(int(t["passes"].sum()), EXPECTED["sum_team_passes"])
        self.assertEqual(len(t), 2 * EXPECTED["n_matches"])

    def test_coverage_warns_never_errors(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cov = op.coverage_report("nla", "2223")
        self.assertEqual(int(cov["gaps"].sum()), EXPECTED["gaps_nla_2223"])
        self.assertTrue(any(issubclass(x.category, op.CoverageWarning) for x in w))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            op.matches("nla", "2223")
        self.assertTrue(any(issubclass(x.category, op.CoverageWarning) for x in w))
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            op.coverage_report("not_a_comp")
        self.assertFalse(any(issubclass(x.category, op.CoverageWarning) for x in w))

    def test_player_season_stats(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            s = op.player_season_stats("nla", "2223")
            s90 = op.player_season_stats("nla", "2223", per90=True, min_minutes=180)
        self.assertEqual(len(s), EXPECTED["n_season_rows_nla_2223"])
        self.assertEqual(int(s["minutes_played"].sum()), EXPECTED["sum_season_minutes_nla_2223"])
        self.assertEqual(int(s["goals"].sum()), EXPECTED["sum_season_goals_nla_2223"])
        self.assertEqual(len(s90), EXPECTED["n_season_rows_nla_2223_min180"])
        best = s90.sort_values(["xg", "player_id"], ascending=[False, True]).iloc[0]
        self.assertEqual(int(best["player_id"]), EXPECTED["top_xg90_player_id_nla_2223"])
        self.assertAlmostEqual(float(best["xg"]), EXPECTED["top_xg90_nla_2223"], places=4)

    def test_player_filter_and_career(self):
        self.assertEqual(op.name_key("  Kylian  Mbappé "), "kylian mbappe")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = op.player_match_stats("nla", "2022/23", player="kylian mbappe")
            s = op.shots("usc", player="Lionel Messi")
            c = op.player_career("Luka Modric")
        self.assertEqual(len(m), EXPECTED["mbappe_matches_nla_2223"])
        self.assertEqual(len(s), EXPECTED["messi_shots_usc"])
        self.assertEqual(len(c), EXPECTED["modric_career_rows"])
        self.assertEqual(int(c["goals"].sum()), EXPECTED["modric_career_goals"])
        self.assertEqual(int(c["minutes_played"].sum()), EXPECTED["modric_career_minutes"])
        self.assertTrue(c["first_match"].is_monotonic_increasing)

    def test_misspelled_player_suggests(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            r = op.player_season_stats(player="Lionel Messsi")
        self.assertEqual(len(r), 0)
        msgs = [str(x.message) for x in w if issubclass(x.category, op.PlayerWarning)]
        self.assertTrue(any("Did you mean: Lionel Messi" in m for m in msgs))
        self.assertEqual(op.suggest_players("Messi")[0], "Lionel Messi")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.assertEqual(len(op.player_career("Zzzz Qqqq")), 0)
        self.assertTrue(any("Check the spelling" in str(x.message) for x in w))

    def test_known_gaps(self):
        self.assertEqual(len(op.known_gaps()), EXPECTED["n_known_gaps"])

    def test_players_teams(self):
        self.assertGreater(len(op.players()), 0)
        self.assertGreater(len(op.teams()), 0)


if __name__ == "__main__":
    unittest.main()
