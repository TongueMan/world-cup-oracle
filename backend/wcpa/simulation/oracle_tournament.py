"""Full 48-team Oracle tournament engine.

This engine is the product-grade path. The existing ``TournamentSimulator`` is
kept for MVP tests and backwards compatibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations

from wcpa.data.repositories.fixture_loader import load_matches, load_narratives, load_teams
from wcpa.data.repositories.postgres_repository import PostgresRepository
from wcpa.data.real_dataset import DataUnavailableError, load_strict_real_dataset
from wcpa.data.sources.web_collectors import SourceSnapshot, WebCollector
from wcpa.debate.debate_runner import DebateRunner
from wcpa.features.feature_builder import build_features
from wcpa.narrative.narrative_engine import compute_narrative_score
from wcpa.prediction.match_predictor import BaselineMatchPredictor
from wcpa.schemas.artifact import ChampionProbability, DataSourceStatus, TournamentPrediction
from wcpa.schemas.match import Match, MatchResult
from wcpa.schemas.narrative import NarrativeProfile
from wcpa.schemas.prediction import MatchPrediction, PredictionContext
from wcpa.schemas.symbolic import SymbolicSignal
from wcpa.schemas.team import Team
from wcpa.schemas.tournament import Bracket, GroupStanding, KnockoutSlot
from wcpa.shared.random_utils import create_rng, derive_rng
from wcpa.shared.config_loader import load_config
from wcpa.shared.paths import PREDICTIONS_DIR
from wcpa.simulation.group_standings import compute_group_standings
from wcpa.simulation.monte_carlo import run_world_cup_monte_carlo
from wcpa.symbolic.symbolic_engine import FixtureSymbolicEngine


FALLBACK_TEAM_ROWS = [
    ("BEL", "Belgium", "UEFA", 8, 1868),
    ("ITA", "Italy", "UEFA", 10, 1835),
    ("URU", "Uruguay", "CONMEBOL", 11, 1818),
    ("COL", "Colombia", "CONMEBOL", 12, 1792),
    ("CRO", "Croatia", "UEFA", 13, 1770),
    ("SUI", "Switzerland", "UEFA", 15, 1740),
    ("DEN", "Denmark", "UEFA", 16, 1735),
    ("AUT", "Austria", "UEFA", 20, 1675),
    ("IRN", "Iran", "AFC", 21, 1660),
    ("SRB", "Serbia", "UEFA", 22, 1655),
    ("SWE", "Sweden", "UEFA", 24, 1640),
    ("UKR", "Ukraine", "UEFA", 25, 1630),
    ("POL", "Poland", "UEFA", 26, 1625),
    ("CAN", "Canada", "CONCACAF", 28, 1605),
    ("TUR", "Turkey", "UEFA", 29, 1600),
    ("NOR", "Norway", "UEFA", 30, 1595),
    ("NGA", "Nigeria", "CAF", 31, 1585),
    ("EGY", "Egypt", "CAF", 33, 1565),
    ("ALG", "Algeria", "CAF", 34, 1560),
    ("TUN", "Tunisia", "CAF", 35, 1548),
    ("CMR", "Cameroon", "CAF", 36, 1540),
    ("GHA", "Ghana", "CAF", 37, 1530),
    ("QAT", "Qatar", "AFC", 38, 1520),
    ("KSA", "Saudi Arabia", "AFC", 39, 1510),
    ("UAE", "United Arab Emirates", "AFC", 40, 1500),
    ("CHN", "China PR", "AFC", 41, 1490),
    ("NZL", "New Zealand", "OFC", 42, 1480),
    ("CRC", "Costa Rica", "CONCACAF", 43, 1470),
    ("PAN", "Panama", "CONCACAF", 44, 1460),
    ("JAM", "Jamaica", "CONCACAF", 45, 1450),
    ("PAR", "Paraguay", "CONMEBOL", 46, 1440),
    ("CHI", "Chile", "CONMEBOL", 47, 1430),
    ("PER", "Peru", "CONMEBOL", 48, 1420),
    ("RSA", "South Africa", "CAF", 49, 1410),
    ("CIV", "Cote d'Ivoire", "CAF", 50, 1400),
    ("MLI", "Mali", "CAF", 51, 1390),
    ("VEN", "Venezuela", "CONMEBOL", 52, 1380),
    ("BOL", "Bolivia", "CONMEBOL", 53, 1370),
]


class OracleTournamentEngine:
    """Runs real-time aware 48-team prediction with agent-ready outputs."""

    def __init__(
        self,
        seed: int = 42,
        mode: str = "balanced",
        monte_carlo_iterations: int | None = None,
    ):
        self.seed = seed
        self.mode = mode
        self.rng = create_rng(seed)
        self.predictor = BaselineMatchPredictor()
        self.symbolic_engine = FixtureSymbolicEngine()
        self.debate_runner = DebateRunner()
        self.repository = PostgresRepository()
        simulation_config = load_config("simulation")
        self.monte_carlo_iterations = monte_carlo_iterations or int(
            simulation_config["monte_carlo"]["iterations"]
        )

    def run(self, precompute_agents: bool = True, strict: bool = True) -> TournamentPrediction:
        snapshots = WebCollector().collect_all()
        self._persist_snapshots(snapshots)
        data_sources = [snapshot.status for snapshot in snapshots]

        if strict:
            try:
                teams, matches, narratives, data_quality_report = load_strict_real_dataset(
                    data_sources
                )
            except DataUnavailableError as exc:
                teams = self._load_48_teams()
                matches = self._load_group_matches(teams)
                narratives = self._load_narratives(teams)
                data_quality_report = exc.report.model_copy(
                    update={
                        "status": "degraded_prediction",
                        "message": (
                            "严格数据校验未通过，已使用现有本地资料和模型先验继续生成"
                            "低置信度预测；缺失项已保留在质量报告中。"
                        ),
                    }
                )
        else:
            teams = self._load_48_teams()
            matches = self._load_group_matches(teams)
            narratives = self._load_narratives(teams)
            from wcpa.schemas.artifact import DataQualityReport

            data_quality_report = DataQualityReport(
                status="demo_only",
                strict=False,
                source_statuses=data_sources,
                message="Demo mode uses fixture/expanded data and is not valid for production prediction.",
            )
        team_map = {team.team_id: team for team in teams}
        narrative_map = {profile.team_id: profile for profile in narratives}
        features = build_features(teams)

        match_predictions: list[MatchPrediction] = []
        match_results: list[MatchResult] = []
        symbolic_signals: list[SymbolicSignal] = []
        group_standings: list[GroupStanding] = []

        group_matches: dict[str, list[Match]] = {}
        for match in matches:
            group_matches.setdefault(match.group or "", []).append(match)

        for group_name, fixtures in sorted(group_matches.items()):
            group_results: list[MatchResult] = []
            match_map = {match.match_id: match for match in fixtures}
            team_ids = sorted(
                {match.home_team_id for match in fixtures}
                | {match.away_team_id for match in fixtures}
            )
            for match in fixtures:
                pred, result, symbolic = self._predict_match(
                    match,
                    team_map,
                    features,
                    allow_draw=True,
                    stage_key=f"group_{match.match_id}",
                )
                match_predictions.append(pred)
                match_results.append(result)
                group_results.append(result)
                symbolic_signals.append(symbolic)

            standing = compute_group_standings(
                group_name,
                team_ids,
                group_results,
                derive_rng(self.rng, f"standings_{group_name}"),
                match_map,
            )
            group_standings.append(self._annotate_standing(standing))

        bracket, knockout_predictions, knockout_results, knockout_symbolics = (
            self._simulate_knockout(group_standings, team_map, features)
        )
        match_predictions.extend(knockout_predictions)
        match_results.extend(knockout_results)
        symbolic_signals.extend(knockout_symbolics)

        debates = []
        if precompute_agents:
            key_predictions = [
                pred
                for pred in knockout_predictions
                if pred.match_id.startswith(("K-SF", "K-F"))
            ]
            match_by_id = {slot.match_id: slot for slot in bracket.slots}
            symbolic_by_id = {signal.match_id: signal for signal in symbolic_signals}
            for pred in key_predictions:
                slot = match_by_id.get(pred.match_id)
                if not slot or not slot.home_team_id or not slot.away_team_id:
                    continue
                match = Match(
                    match_id=slot.match_id,
                    stage=slot.round,
                    home_team_id=slot.home_team_id,
                    away_team_id=slot.away_team_id,
                    status=slot.status,
                )
                debates.append(
                    self.debate_runner.run_debate(
                        pred.match_id,
                        pred,
                        match=match,
                        home=team_map[slot.home_team_id],
                        away=team_map[slot.away_team_id],
                        symbolic_signal=symbolic_by_id.get(pred.match_id),
                        narratives=[
                            narrative_map.get(slot.home_team_id, self._default_narrative(slot.home_team_id)).model_dump(mode="json"),
                            narrative_map.get(slot.away_team_id, self._default_narrative(slot.away_team_id)).model_dump(mode="json"),
                        ],
                    )
                )

        probabilities = self._champion_probabilities(teams, matches, features)
        dark_horses = self._dark_horses(teams, narratives)
        upset_alerts = self._upset_alerts(match_predictions)
        champion_path = self._champion_path(bracket)

        artifact = TournamentPrediction(
            edition="2026",
            seed=self.seed,
            mode=self.mode,
            artifact_version="3.0.0",
            generated_at=datetime.now(timezone.utc),
            group_standings=group_standings,
            bracket=bracket,
            match_predictions=match_predictions,
            match_results=[result.model_dump(mode="json") for result in match_results],
            champion_team_id=bracket.champion_team_id,
            runner_up_team_id=bracket.runner_up_team_id,
            semifinalists=self._semifinalists(bracket),
            rational_champion=bracket.champion_team_id,
            narrative_champion=dark_horses[0]["team_id"] if dark_horses else bracket.champion_team_id,
            symbolic_champion=upset_alerts[0]["winner_team_id"] if upset_alerts else bracket.champion_team_id,
            narratives=narratives,
            symbolic_signals=symbolic_signals,
            debate_transcripts=debates,
            champion_probabilities=probabilities,
            upset_alerts=upset_alerts,
            dark_horses=dark_horses,
            data_sources=data_sources,
            champion_path=champion_path,
            path_reconstruction_notes=self._path_notes(data_sources),
            data_verified=data_quality_report.status == "ready",
            data_quality_report=data_quality_report,
        )
        return artifact

    def run_and_save(
        self, precompute_agents: bool = True, strict: bool = True
    ) -> TournamentPrediction:
        artifact = self.run(precompute_agents=precompute_agents, strict=strict)
        PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = PREDICTIONS_DIR / "oracle-tournament-run.json"
        path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        self.repository.save_prediction(artifact)
        return artifact

    def _load_48_teams(self) -> list[Team]:
        teams = list(load_teams())
        existing = {team.team_id for team in teams}
        for team_id, name, confed, rank, elo in FALLBACK_TEAM_ROWS:
            if len(teams) >= 48:
                break
            if team_id in existing:
                continue
            quality = "C"
            teams.append(
                Team(
                    team_id=team_id,
                    name=name,
                    confederation=confed,
                    fifa_rank=rank,
                    elo_rating=elo,
                    recent_form_score=max(0.35, min(0.86, 1 - rank / 95)),
                    attack_score=max(0.35, min(0.88, elo / 2350)),
                    defense_score=max(0.35, min(0.86, elo / 2450)),
                    squad_health_score=0.78,
                    world_cup_experience_score=max(0.35, min(0.85, 1 - rank / 100)),
                    data_quality=quality,
                )
            )
        return sorted(teams[:48], key=lambda team: team.fifa_rank)

    def _load_group_matches(self, teams: list[Team]) -> list[Match]:
        source_matches = load_matches()
        if len({match.group for match in source_matches if match.group}) >= 12:
            return source_matches

        groups = {chr(ord("A") + idx): [] for idx in range(12)}
        for idx, team in enumerate(teams):
            groups[chr(ord("A") + (idx % 12))].append(team.team_id)

        matches: list[Match] = []
        counter = 1
        for group, team_ids in groups.items():
            for home, away in combinations(team_ids, 2):
                matches.append(
                    Match(
                        match_id=f"G-{group}-{counter:03d}",
                        stage="group",
                        group=group,
                        home_team_id=home,
                        away_team_id=away,
                        venue="World Cup 2026",
                        source="fixture_expansion",
                        status="scheduled",
                    )
                )
                counter += 1
        return matches

    def _load_narratives(self, teams: list[Team]) -> list[NarrativeProfile]:
        existing = {profile.team_id: profile for profile in load_narratives()}
        profiles: list[NarrativeProfile] = []
        for team in teams:
            profile = existing.get(team.team_id) or self._default_narrative(team.team_id)
            score = compute_narrative_score(profile)
            profiles.append(profile.model_copy(update={"narrative_score": round(score, 4)}))
        return profiles

    def _default_narrative(self, team_id: str) -> NarrativeProfile:
        return NarrativeProfile(
            team_id=team_id,
            media_heat_score=0.5,
            morale_score=0.5,
            dark_horse_score=0.45,
            pressure_score=0.45,
            destiny_score=0.5,
            fan_momentum_score=0.5,
            tags=["fallback_narrative"],
        )

    def _predict_match(
        self,
        match: Match,
        team_map: dict[str, Team],
        features: dict,
        allow_draw: bool,
        stage_key: str,
    ) -> tuple[MatchPrediction, MatchResult, SymbolicSignal]:
        home_team = team_map[match.home_team_id]
        away_team = team_map[match.away_team_id]
        structured_available = all(
            team.data_quality in {"A", "B", "C"} for team in (home_team, away_team)
        )
        missing_fields = []
        if not all(team.verified for team in (home_team, away_team)):
            missing_fields.append("verified_external_team_data")
        context = PredictionContext(
            structured_data_available=structured_available,
            missing_fields=missing_fields,
        )
        pred = self.predictor.predict(
            match,
            home_team,
            away_team,
            features[match.home_team_id],
            features[match.away_team_id],
            derive_rng(self.rng, stage_key),
            allow_draw=allow_draw,
            context=context,
        )
        sampled_prediction = self.predictor.predict(
            match,
            home_team,
            away_team,
            features[match.home_team_id],
            features[match.away_team_id],
            derive_rng(self.rng, f"{stage_key}_sample"),
            allow_draw=allow_draw,
            context=context,
            sample_result=True,
        )
        symbolic = self.symbolic_engine.generate_signal(
            match.match_id,
            match.home_team_id,
            match.away_team_id,
            derive_rng(self.rng, f"symbolic_{match.match_id}"),
        )
        upset_index = self._compute_upset_index(pred, symbolic, team_map, match)
        pred = pred.model_copy(
            update={
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
                "upset_index": upset_index,
                "symbolic_summary": self._symbolic_hint(symbolic),
                "narrative_summary": "叙事轨用于提示士气、压力和黑马变量。",
                "tactical_summary": "战术轨依据攻防强度差异生成克制判断。",
            }
        )
        hs, aways = map(int, sampled_prediction.predicted_score.split("-"))
        result = MatchResult(
            match_id=match.match_id,
            home_score=hs,
            away_score=aways,
            winner_team_id=sampled_prediction.winner_team_id,
            went_to_penalties=(not allow_draw and hs == aways),
            source=pred.source,
        )
        return pred, result, symbolic

    def _simulate_knockout(
        self,
        group_standings: list[GroupStanding],
        team_map: dict[str, Team],
        features: dict,
    ) -> tuple[Bracket, list[MatchPrediction], list[MatchResult], list[SymbolicSignal]]:
        qualified = self._qualified_32(group_standings)
        queue = list(qualified)
        round_sizes = [("R32", 16), ("R16", 8), ("QF", 4), ("SF", 2), ("Final", 1)]
        slots: list[KnockoutSlot] = []
        predictions: list[MatchPrediction] = []
        results: list[MatchResult] = []
        symbolics: list[SymbolicSignal] = []

        for round_name, match_count in round_sizes:
            next_queue: list[str] = []
            pairings = [(queue[i], queue[-i - 1]) for i in range(match_count)]
            for idx, (home_id, away_id) in enumerate(pairings, 1):
                match_id = f"K-{round_name}-{idx:03d}"
                match = Match(
                    match_id=match_id,
                    stage=round_name,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    source="oracle_engine",
                    status="predicted",
                )
                pred, result, symbolic = self._predict_match(
                    match, team_map, features, False, f"{round_name}_{idx}"
                )
                predictions.append(pred)
                results.append(result)
                symbolics.append(symbolic)
                next_queue.append(result.winner_team_id or home_id)
                slots.append(
                    KnockoutSlot(
                        round=round_name,
                        match_id=match_id,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        home_source=f"{round_name}_seed_{idx}",
                        away_source=f"{round_name}_seed_{len(queue) - idx + 1}",
                        home_score=result.home_score,
                        away_score=result.away_score,
                        winner_team_id=result.winner_team_id,
                        went_to_penalties=result.went_to_penalties,
                        status="predicted",
                        upset_index=pred.upset_index,
                        symbolic_hint=self._symbolic_hint(symbolic),
                    )
                )
            queue = next_queue

        final = next(slot for slot in slots if slot.round == "Final")
        champion = final.winner_team_id
        runner_up = final.away_team_id if champion == final.home_team_id else final.home_team_id
        return Bracket(slots=slots, champion_team_id=champion, runner_up_team_id=runner_up), predictions, results, symbolics

    def _qualified_32(self, standings: list[GroupStanding]) -> list[str]:
        first_two: list[str] = []
        thirds = []
        for standing in standings:
            rows = standing.rows
            first_two.extend([rows[0].team_id, rows[1].team_id])
            thirds.append(rows[2])
        best_thirds = sorted(
            thirds,
            key=lambda row: (-row.points, -row.goal_difference, -row.goals_for, row.team_id),
        )[:8]
        qualified = first_two + [row.team_id for row in best_thirds]
        return qualified[:32]

    def _annotate_standing(self, standing: GroupStanding) -> GroupStanding:
        rows = []
        for row in standing.rows:
            if row.rank <= 2:
                status = "qualified"
                prob = 0.9
            elif row.rank == 3:
                status = "third_place_contender"
                prob = 0.45
            else:
                status = "eliminated"
                prob = 0.1
            rows.append(row.model_copy(update={"qualification_status": status, "advancement_probability": prob}))
        return standing.model_copy(update={"rows": rows})

    def _champion_probabilities(
        self,
        teams: list[Team],
        matches: list[Match],
        features: dict,
    ) -> list[ChampionProbability]:
        return run_world_cup_monte_carlo(
            teams,
            matches,
            self.predictor,
            features,
            n_sims=self.monte_carlo_iterations,
            seed=self.seed,
        )

    def _dark_horses(self, teams: list[Team], narratives: list[NarrativeProfile]) -> list[dict]:
        team_map = {team.team_id: team for team in teams}
        rows = []
        for profile in narratives:
            team = team_map[profile.team_id]
            score = profile.dark_horse_score * 0.6 + min(1.0, team.fifa_rank / 55) * 0.4
            rows.append({"team_id": team.team_id, "score": round(score, 4), "tags": profile.tags})
        return sorted(rows, key=lambda row: row["score"], reverse=True)[:8]

    def _upset_alerts(self, predictions: list[MatchPrediction]) -> list[dict]:
        rows = [
            {
                "match_id": pred.match_id,
                "winner_team_id": pred.winner_team_id,
                "upset_index": pred.upset_index,
                "summary": pred.symbolic_summary or "爆冷风险由实力差和象征信号综合生成。",
            }
            for pred in predictions
            if pred.upset_index >= 0.25
        ]
        return sorted(rows, key=lambda row: row["upset_index"], reverse=True)[:10]

    def _compute_upset_index(
        self,
        pred: MatchPrediction,
        symbolic: SymbolicSignal,
        team_map: dict[str, Team],
        match: Match,
    ) -> float:
        rank_gap = abs(team_map[match.home_team_id].fifa_rank - team_map[match.away_team_id].fifa_rank)
        base = min(0.45, rank_gap / 120)
        symbolic_risk = symbolic.iching.upset_risk if symbolic.iching else 0.5
        return round(min(1.0, base * 0.5 + (1 - pred.confidence) * 0.3 + symbolic_risk * 0.2), 4)

    def _symbolic_hint(self, symbolic: SymbolicSignal) -> str:
        gua = symbolic.iching.gua if symbolic.iching else "未知"
        risk = symbolic.iching.upset_risk if symbolic.iching else 0.5
        return f"{gua}提示{'高波动' if risk >= 0.6 else '谨慎推进'}"

    def _semifinalists(self, bracket: Bracket) -> list[str]:
        semifinalists: list[str] = []
        for slot in bracket.slots:
            if slot.round == "SF":
                semifinalists.extend([slot.home_team_id, slot.away_team_id])
        return [team for team in semifinalists if team]

    def _champion_path(self, bracket: Bracket) -> list[dict]:
        champion = bracket.champion_team_id
        if not champion:
            return []
        path = []
        for slot in bracket.slots:
            if slot.winner_team_id == champion:
                path.append(
                    {
                        "round": slot.round,
                        "match_id": slot.match_id,
                        "home_team_id": slot.home_team_id,
                        "away_team_id": slot.away_team_id,
                        "score": f"{slot.home_score}-{slot.away_score}",
                    }
                )
        return path

    def _path_notes(self, data_sources: list[DataSourceStatus]) -> list[str]:
        if any(source.status == "ok" for source in data_sources):
            return ["已记录外部数据源快照；真实赛果会在标准化后锁定并触发路径重构。"]
        return ["当前使用 fixture/扩展数据兜底；未锁定真实赛果。"]

    def _persist_snapshots(self, snapshots: list[SourceSnapshot]) -> None:
        for snapshot in snapshots:
            self.repository.save_source_snapshot(
                snapshot.source_key,
                snapshot.url,
                snapshot.status.status,
                snapshot.status.credibility,
                snapshot.raw,
                snapshot.status.message,
            )
