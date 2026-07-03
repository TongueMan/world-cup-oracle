"""Bing Sports collector parsing regressions."""

from wcpa.data.sources.bing_worldcup import BingSportsWorldCupCollector, _stable_team_id


def test_parse_scheduled_match_label():
    collector = BingSportsWorldCupCollector()
    label = (
        "\u67e5\u770b \u6fb3\u5927\u5229\u4e9a \u5bf9\u9635 \u57c3\u53ca "
        "\u7684\u8be6\u7ec6\u4fe1\u606f, 32 \u5f3a\u8d5b, \u660e\u5929, 02:00"
    )

    row = collector._parse_match_label(label)

    assert row is not None
    assert row["home_team_id"] == "AUS"
    assert row["away_team_id"] == "EGY"
    assert row["stage"] == "R32"
    assert row["status"] == "scheduled"
    assert row["is_actual"] is False


def test_parse_final_match_label_locks_real_result():
    collector = BingSportsWorldCupCollector()
    label = (
        "\u67e5\u770b \u8377\u5170 \u5bf9\u9635 \u745e\u5178 "
        "\u7684\u8be6\u7ec6\u4fe1\u606f, \u7ec4 F, \u8377\u5170 5, "
        "\u745e\u5178 1, \u5168\u573a, 6\u670821\u65e5\u5468\u65e5"
    )

    row = collector._parse_match_label(label)

    assert row is not None
    assert row["group"] == "F"
    assert row["home_score"] == 5
    assert row["away_score"] == 1
    assert row["winner_name"] == "\u8377\u5170"
    assert row["status"] == "final"
    assert row["is_actual"] is True


def test_placeholders_do_not_become_real_team_ids():
    collector = BingSportsWorldCupCollector()
    label = (
        "\u67e5\u770b W89 \u5bf9\u9635 W90 \u7684\u8be6\u7ec6\u4fe1\u606f, "
        "\u56db\u5206\u4e4b\u4e00\u51b3\u8d5b, 7\u670810\u65e5, 04:00"
    )

    row = collector._parse_match_label(label)

    assert row is not None
    assert row["home_team_id"] == "W89"
    assert row["away_team_id"] == "W90"
    assert row["home_is_placeholder"] is True
    assert row["away_is_placeholder"] is True
    assert _stable_team_id("\u963f\u6839\u5ef7") == "ARG"
