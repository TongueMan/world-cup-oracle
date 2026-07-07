"""Historical men's World Cup data service."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from wcpa.shared.paths import DATA_DIR

HISTORY_FILE = DATA_DIR / "knowledge" / "worldcup" / "history.json"
HISTORY_SEED_FILE = Path(__file__).with_name("history_seed.json")


class WorldCupHistoryService:
    def __init__(self, history_file=HISTORY_FILE):
        self.history_file = history_file

    def list_editions(self) -> list[dict[str, Any]]:
        return [_enrich_edition(row) for row in self._payload()["editions"]]

    def get_edition(self, year: int) -> dict[str, Any] | None:
        edition = next((row for row in self.list_editions() if row["year"] == year), None)
        if not edition:
            return None
        matches = self.list_matches(year=year)
        stages = sorted({row["stage"] for row in matches if row.get("stage")})
        return edition | {"stages": stages, "matches": matches}

    def list_matches(
        self,
        year: int | None = None,
        team: str | None = None,
        stage: str | None = None,
        home_team: str | None = None,
        away_team: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = [_enrich_match(row) for row in self._payload()["matches"]]
        result = []
        paired_team_search = bool(_normalize_search_value(home_team) and _normalize_search_value(away_team))
        for row in rows:
            if year is not None and row.get("year") != year:
                continue
            if stage and row.get("stage") != stage:
                continue
            if team and not (_team_matches(row.get("home_team"), team) or _team_matches(row.get("away_team"), team)):
                continue
            if paired_team_search:
                if not _team_equals(row.get("home_team"), home_team):
                    continue
                if not _team_equals(row.get("away_team"), away_team):
                    continue
            else:
                if home_team and not _team_matches(row.get("home_team"), home_team):
                    continue
                if away_team and not _team_matches(row.get("away_team"), away_team):
                    continue
            result.append(row)
        return sorted(result, key=lambda item: (item.get("date") or "", item.get("match_id") or ""))

    def list_team_matches(self, team: str) -> list[dict[str, Any]]:
        return self.list_matches(team=team)

    def list_finals(self) -> list[dict[str, Any]]:
        return [_enrich_match(row) for row in self._payload()["finals"]]

    def _payload(self) -> dict[str, Any]:
        return _load_history_payload(str(self.history_file))


@lru_cache(maxsize=4)
def _load_history_payload(path: str) -> dict[str, Any]:
    history_path = Path(path)
    if not history_path.exists() and path == str(HISTORY_FILE):
        history_path = HISTORY_SEED_FILE
    if not history_path.exists():
        return {"source": {}, "editions": [], "matches": [], "finals": []}
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    return {
        "source": payload.get("source") or {},
        "editions": payload.get("editions") or [],
        "matches": payload.get("matches") or [],
        "finals": payload.get("finals") or [],
    }


def _normalize_search_value(value: str | None) -> str:
    return (value or "").strip().casefold()


def _enrich_edition(row: dict[str, Any]) -> dict[str, Any]:
    champion = _team_meta(row.get("champion"))
    runner_up = _team_meta(row.get("runner_up"))
    hosts = [_team_meta(country) for country in row.get("host_countries", [])]
    return row | {
        "name_zh": f"{row.get('year')} 年世界杯",
        "host_countries_zh": [host["zh"] for host in hosts],
        "host_flag_codes": [host["flag_code"] for host in hosts if host["flag_code"]],
        "champion_zh": champion["zh"],
        "champion_flag_code": champion["flag_code"],
        "runner_up_zh": runner_up["zh"],
        "runner_up_flag_code": runner_up["flag_code"],
    }


def _enrich_match(row: dict[str, Any]) -> dict[str, Any]:
    home = _team_meta(row.get("home_team"))
    away = _team_meta(row.get("away_team"))
    winner = _team_meta(row.get("winner_team"))
    champion = _team_meta(row.get("champion"))
    runner_up = _team_meta(row.get("runner_up"))
    stage = row.get("stage") or ""
    round_name = row.get("round") or ""
    return row | {
        "stage_zh": _stage_zh(stage, round_name),
        "round_zh": _round_zh(round_name, stage),
        "group_name_zh": _group_zh(row.get("group_name")),
        "venue_zh": _VENUE_ZH.get(row.get("venue") or "", row.get("venue")),
        "city_zh": _CITY_ZH.get(row.get("city") or "", row.get("city")),
        "home_team_zh": home["zh"],
        "home_flag_code": home["flag_code"],
        "away_team_zh": away["zh"],
        "away_flag_code": away["flag_code"],
        "winner_team_zh": winner["zh"] if row.get("winner_team") else None,
        "winner_flag_code": winner["flag_code"] if row.get("winner_team") else None,
        "champion_zh": champion["zh"] if row.get("champion") else None,
        "champion_flag_code": champion["flag_code"] if row.get("champion") else None,
        "runner_up_zh": runner_up["zh"] if row.get("runner_up") else None,
        "runner_up_flag_code": runner_up["flag_code"] if row.get("runner_up") else None,
    }


def _team_meta(name: str | None) -> dict[str, Any]:
    if not name:
        return {"zh": None, "flag_code": None, "aliases": []}
    meta = _TEAM_META.get(name)
    if meta:
        return {
            "zh": meta["zh"],
            "flag_code": meta.get("flag_code"),
            "aliases": [name, meta["zh"], *(meta.get("aliases") or [])],
        }
    return {"zh": name, "flag_code": None, "aliases": [name]}


def _team_matches(team_name: str | None, query: str) -> bool:
    query_key = _normalize_search_value(query)
    if not query_key:
        return True
    meta = _team_meta(team_name)
    return any(query_key in _normalize_search_value(alias) for alias in meta["aliases"] if alias)


def _team_equals(team_name: str | None, query: str | None) -> bool:
    query_key = _normalize_search_value(query)
    if not query_key:
        return True
    meta = _team_meta(team_name)
    return any(query_key == _normalize_search_value(alias) for alias in meta["aliases"] if alias)


def _stage_zh(stage: str, round_name: str) -> str:
    if stage == "group":
        return "小组赛"
    return {
        "R16": "十六强",
        "QF": "四分之一决赛",
        "SF": "半决赛",
        "ThirdPlace": "季军赛",
        "Final": "决赛",
        "FinalRound": "决赛轮",
    }.get(stage, _round_zh(round_name, stage))


def _round_zh(round_name: str, stage: str) -> str:
    if not round_name:
        return _stage_zh(stage, "") if stage else ""
    if round_name.startswith("Matchday"):
        number = round_name.replace("Matchday", "").strip()
        return f"第 {number} 比赛日" if number else "比赛日"
    return {
        "Round of 16": "十六强",
        "Quarter-finals": "四分之一决赛",
        "Semi-finals": "半决赛",
        "Match for third place": "季军赛",
        "Final": "决赛",
        "Final Round": "决赛轮",
    }.get(round_name, round_name)


def _group_zh(group_name: str | None) -> str | None:
    if not group_name:
        return None
    return group_name.replace("Group", "小组")


_TEAM_META: dict[str, dict[str, Any]] = {
    "Algeria": {"zh": "阿尔及利亚", "flag_code": "dz"},
    "Angola": {"zh": "安哥拉", "flag_code": "ao"},
    "Argentina": {"zh": "阿根廷", "flag_code": "ar"},
    "Australia": {"zh": "澳大利亚", "flag_code": "au"},
    "Austria": {"zh": "奥地利", "flag_code": "at"},
    "Belgium": {"zh": "比利时", "flag_code": "be"},
    "Bolivia": {"zh": "玻利维亚", "flag_code": "bo"},
    "Bosnia-Herzegovina": {"zh": "波黑", "flag_code": "ba", "aliases": ["Bosnia and Herzegovina"]},
    "Brazil": {"zh": "巴西", "flag_code": "br"},
    "Bulgaria": {"zh": "保加利亚", "flag_code": "bg"},
    "Cameroon": {"zh": "喀麦隆", "flag_code": "cm"},
    "Canada": {"zh": "加拿大", "flag_code": "ca"},
    "Chile": {"zh": "智利", "flag_code": "cl"},
    "China": {"zh": "中国", "flag_code": "cn"},
    "Colombia": {"zh": "哥伦比亚", "flag_code": "co"},
    "Costa Rica": {"zh": "哥斯达黎加", "flag_code": "cr"},
    "Croatia": {"zh": "克罗地亚", "flag_code": "hr"},
    "Cuba": {"zh": "古巴", "flag_code": "cu"},
    "Czech Republic": {"zh": "捷克", "flag_code": "cz"},
    "Czechoslovakia": {"zh": "捷克斯洛伐克", "flag_code": "cz", "aliases": ["捷克"]},
    "Côte d'Ivoire": {"zh": "科特迪瓦", "flag_code": "ci", "aliases": ["Cote d'Ivoire", "象牙海岸"]},
    "Denmark": {"zh": "丹麦", "flag_code": "dk"},
    "Dutch East Indies": {"zh": "荷属东印度", "flag_code": "id", "aliases": ["印度尼西亚"]},
    "East Germany": {"zh": "东德", "flag_code": "de", "aliases": ["德国"]},
    "Ecuador": {"zh": "厄瓜多尔", "flag_code": "ec"},
    "Egypt": {"zh": "埃及", "flag_code": "eg"},
    "El Salvador": {"zh": "萨尔瓦多", "flag_code": "sv"},
    "England": {"zh": "英格兰", "flag_code": "gb-eng"},
    "France": {"zh": "法国", "flag_code": "fr"},
    "Germany": {"zh": "德国", "flag_code": "de"},
    "Ghana": {"zh": "加纳", "flag_code": "gh"},
    "Greece": {"zh": "希腊", "flag_code": "gr"},
    "Haiti": {"zh": "海地", "flag_code": "ht"},
    "Honduras": {"zh": "洪都拉斯", "flag_code": "hn"},
    "Hungary": {"zh": "匈牙利", "flag_code": "hu"},
    "Iceland": {"zh": "冰岛", "flag_code": "is"},
    "Iran": {"zh": "伊朗", "flag_code": "ir"},
    "Iraq": {"zh": "伊拉克", "flag_code": "iq"},
    "Ireland": {"zh": "爱尔兰", "flag_code": "ie"},
    "Israel": {"zh": "以色列", "flag_code": "il"},
    "Italy": {"zh": "意大利", "flag_code": "it"},
    "Jamaica": {"zh": "牙买加", "flag_code": "jm"},
    "Japan": {"zh": "日本", "flag_code": "jp"},
    "Kuwait": {"zh": "科威特", "flag_code": "kw"},
    "Mexico": {"zh": "墨西哥", "flag_code": "mx"},
    "Morocco": {"zh": "摩洛哥", "flag_code": "ma"},
    "Netherlands": {"zh": "荷兰", "flag_code": "nl"},
    "New Zealand": {"zh": "新西兰", "flag_code": "nz"},
    "Nigeria": {"zh": "尼日利亚", "flag_code": "ng"},
    "North Korea": {"zh": "朝鲜", "flag_code": "kp"},
    "Northern Ireland": {"zh": "北爱尔兰", "flag_code": "gb-nir"},
    "Norway": {"zh": "挪威", "flag_code": "no"},
    "Panama": {"zh": "巴拿马", "flag_code": "pa"},
    "Paraguay": {"zh": "巴拉圭", "flag_code": "py"},
    "Peru": {"zh": "秘鲁", "flag_code": "pe"},
    "Poland": {"zh": "波兰", "flag_code": "pl"},
    "Portugal": {"zh": "葡萄牙", "flag_code": "pt"},
    "Qatar": {"zh": "卡塔尔", "flag_code": "qa"},
    "Romania": {"zh": "罗马尼亚", "flag_code": "ro"},
    "Russia": {"zh": "俄罗斯", "flag_code": "ru"},
    "Saudi Arabia": {"zh": "沙特阿拉伯", "flag_code": "sa"},
    "Scotland": {"zh": "苏格兰", "flag_code": "gb-sct"},
    "Senegal": {"zh": "塞内加尔", "flag_code": "sn"},
    "Serbia": {"zh": "塞尔维亚", "flag_code": "rs"},
    "Serbia and Montenegro": {"zh": "塞尔维亚和黑山", "flag_code": "rs", "aliases": ["塞尔维亚"]},
    "Slovakia": {"zh": "斯洛伐克", "flag_code": "sk"},
    "Slovenia": {"zh": "斯洛文尼亚", "flag_code": "si"},
    "South Africa": {"zh": "南非", "flag_code": "za"},
    "South Korea": {"zh": "韩国", "flag_code": "kr", "aliases": ["Korea Republic"]},
    "Soviet Union": {"zh": "苏联", "flag_code": "ru", "aliases": ["俄罗斯"]},
    "Spain": {"zh": "西班牙", "flag_code": "es"},
    "Sweden": {"zh": "瑞典", "flag_code": "se"},
    "Switzerland": {"zh": "瑞士", "flag_code": "ch"},
    "Togo": {"zh": "多哥", "flag_code": "tg"},
    "Trinidad and Tobago": {"zh": "特立尼达和多巴哥", "flag_code": "tt"},
    "Tunisia": {"zh": "突尼斯", "flag_code": "tn"},
    "Turkey": {"zh": "土耳其", "flag_code": "tr"},
    "USA": {"zh": "美国", "flag_code": "us", "aliases": ["United States", "US"]},
    "Ukraine": {"zh": "乌克兰", "flag_code": "ua"},
    "United Arab Emirates": {"zh": "阿联酋", "flag_code": "ae"},
    "United States": {"zh": "美国", "flag_code": "us", "aliases": ["USA", "US"]},
    "Uruguay": {"zh": "乌拉圭", "flag_code": "uy"},
    "Wales": {"zh": "威尔士", "flag_code": "gb-wls"},
    "West Germany": {"zh": "西德", "flag_code": "de", "aliases": ["德国"]},
    "Yugoslavia": {"zh": "南斯拉夫", "flag_code": "rs", "aliases": ["塞尔维亚"]},
    "Zaire": {"zh": "扎伊尔", "flag_code": "cd", "aliases": ["刚果民主共和国"]},
}

_CITY_ZH = {
    "A Coruña": "拉科鲁尼亚",
    "Al Khor": "豪尔",
    "Al Rayyan": "赖扬",
    "Al Wakrah": "沃克拉",
    "Alicante": "阿利坎特",
    "Antibes": "昂蒂布",
    "Arica": "阿里卡",
    "Barcelona": "巴塞罗那",
    "Bari": "巴里",
    "Basel": "巴塞尔",
    "Belo Horizonte": "贝洛奥里藏特",
    "Berlin": "柏林",
    "Bern": "伯尔尼",
    "Bilbao": "毕尔巴鄂",
    "Birmingham": "伯明翰",
    "Bloemfontein": "布隆方丹",
    "Bologna": "博洛尼亚",
    "Bordeaux": "波尔多",
    "Brasília": "巴西利亚",
    "Buenos Aires": "布宜诺斯艾利斯",
    "Busan": "釜山",
    "Cagliari": "卡利亚里",
    "Cape Town": "开普敦",
    "Chicago": "芝加哥",
    "Córdoba": "科尔多瓦",
    "Cuiabá": "库亚巴",
    "Curitiba": "库里蒂巴",
    "Daegu": "大邱",
    "Daejeon": "大田",
    "Dallas": "达拉斯",
    "Doha": "多哈",
    "Dortmund": "多特蒙德",
    "Durban": "德班",
    "Düsseldorf": "杜塞尔多夫",
    "East Rutherford": "东卢瑟福",
    "Ekaterinburg": "叶卡捷琳堡",
    "Florence": "佛罗伦萨",
    "Fortaleza": "福塔莱萨",
    "Foxborough": "福克斯伯勒",
    "Frankfurt": "法兰克福",
    "Gelsenkirchen": "盖尔森基兴",
    "Geneva": "日内瓦",
    "Genoa": "热那亚",
    "Gijón": "希洪",
    "Gothenburg": "哥德堡",
    "Guadalajara": "瓜达拉哈拉",
    "Gwangju": "光州",
    "Hamburg": "汉堡",
    "Hannover": "汉诺威",
    "Ibaraki": "茨城",
    "Incheon": "仁川",
    "Johannesburg": "约翰内斯堡",
    "Kaiserslautern": "凯泽斯劳滕",
    "Kaliningrad": "加里宁格勒",
    "Kazan": "喀山",
    "Kobe": "神户",
    "Köln": "科隆",
    "Lens": "朗斯",
    "Le Havre": "勒阿弗尔",
    "Leipzig": "莱比锡",
    "León": "莱昂",
    "Lille": "里尔",
    "Liverpool": "利物浦",
    "London": "伦敦",
    "Lugano": "卢加诺",
    "Lusail": "卢赛尔",
    "Lyon": "里昂",
    "Madrid": "马德里",
    "Málaga": "马拉加",
    "Manaus": "马瑙斯",
    "Mar del Plata": "马德普拉塔",
    "Marseille": "马赛",
    "Mendoza": "门多萨",
    "Mexico City": "墨西哥城",
    "Milan": "米兰",
    "Montevideo": "蒙得维的亚",
    "Monterrey": "蒙特雷",
    "Montpellier": "蒙彼利埃",
    "Moscow": "莫斯科",
    "München": "慕尼黑",
    "Munich": "慕尼黑",
    "Nantes": "南特",
    "Naples": "那不勒斯",
    "Natal": "纳塔尔",
    "Nezahualcóyotl": "内萨瓦尔科约特尔",
    "Nizhny Novgorod": "下诺夫哥罗德",
    "Nürnberg": "纽伦堡",
    "Ōita": "大分",
    "Orlando": "奥兰多",
    "Osaka": "大阪",
    "Oviedo": "奥维耶多",
    "Palermo": "巴勒莫",
    "Paris": "巴黎",
    "Pasadena": "帕萨迪纳",
    "Polokwane": "波罗克瓦尼",
    "Pontiac": "庞蒂亚克",
    "Port Elizabeth": "伊丽莎白港",
    "Porto Alegre": "阿雷格里港",
    "Pretoria": "比勒陀利亚",
    "Puebla": "普埃布拉",
    "Querétaro": "克雷塔罗",
    "Rancagua": "兰卡瓜",
    "Recife": "累西腓",
    "Reims": "兰斯",
    "Rio de Janeiro": "里约热内卢",
    "Rome": "罗马",
    "Rosario": "罗萨里奥",
    "Rostov-on-Don": "顿河畔罗斯托夫",
    "Rustenburg": "勒斯滕堡",
    "Saint-Denis": "圣但尼",
    "Saint Petersburg": "圣彼得堡",
    "Saint-Étienne": "圣艾蒂安",
    "Salvador": "萨尔瓦多",
    "Sapporo": "札幌",
    "Saransk": "萨兰斯克",
    "Seoul": "首尔",
    "Seville": "塞维利亚",
    "Sheffield": "谢菲尔德",
    "Sochi": "索契",
    "Solna": "索尔纳",
    "Santiago": "圣地亚哥",
    "St. Petersburg": "圣彼得堡",
    "Stanford": "斯坦福",
    "Strasbourg": "斯特拉斯堡",
    "Stuttgart": "斯图加特",
    "Suwon": "水原",
    "São Paulo": "圣保罗",
    "Toluca": "托卢卡",
    "Toulouse": "图卢兹",
    "Trieste": "的里雅斯特",
    "Turin": "都灵",
    "Udine": "乌迪内",
    "Ulsan": "蔚山",
    "Valencia": "瓦伦西亚",
    "Valladolid": "巴利亚多利德",
    "Verona": "维罗纳",
    "Vigo": "维戈",
    "Viña del Mar": "比尼亚德尔马",
    "Volgograd": "伏尔加格勒",
    "Washington": "华盛顿",
    "West Berlin": "西柏林",
    "Yokohama": "横滨",
    "Zaragoza": "萨拉戈萨",
    "Zürich": "苏黎世",
}

_VENUE_ZH = {
    "AOL Arena": "AOL球场",
    "AWD-Arena": "AWD竞技场",
    "Ahmad bin Ali Stadium": "艾哈迈德·本·阿里体育场",
    "Al Bayt Stadium": "海湾球场",
    "Al Janoub Stadium": "贾努布球场",
    "Al Thumama Stadium": "图玛玛球场",
    "Allianz Arena": "安联球场",
    "Arena Amazônia": "亚马逊竞技场",
    "Arena Fonte Nova": "新水源竞技场",
    "Arena Pantanal": "潘塔纳尔竞技场",
    "Arena Pernambuco": "伯南布哥竞技场",
    "Arena da Baixada": "拜沙达竞技场",
    "Arena de São Paulo": "圣保罗竞技场",
    "Ayresome Park": "艾尔索姆公园球场",
    "Camp Nou": "诺坎普球场",
    "Cape Town Stadium": "开普敦体育场",
    "Citrus Bowl": "柑橘碗球场",
    "Commerzbank-Arena": "商业银行竞技场",
    "Cotton Bowl": "棉花碗球场",
    "Daegu World Cup Stadium": "大邱世界杯体育场",
    "Daejeon World Cup Stadium": "大田世界杯体育场",
    "Education City Stadium": "教育城体育场",
    "Ekaterinburg Arena": "叶卡捷琳堡竞技场",
    "Ellis Park Stadium": "埃利斯公园体育场",
    "Estadio Azteca": "阿兹特克体育场",
    "Estadio Centenario": "世纪体育场",
    "Estadio Jalisco": "哈利斯科体育场",
    "Estadio Monumental": "纪念碑体育场",
    "Estadio Nacional": "国家体育场",
    "Estadio Olímpico Universitario": "大学奥林匹克体育场",
    "Estadio Parque Central": "中央公园体育场",
    "Estadio Santiago Bernabéu": "圣地亚哥·伯纳乌球场",
    "Estádio Beira-Rio": "贝拉里奥球场",
    "Estádio Castelão": "卡斯特朗体育场",
    "Estádio Mineirão": "米内罗体育场",
    "Estádio Nacional Mané Garrincha": "马内·加林查国家体育场",
    "Estádio das Dunas": "沙丘竞技场",
    "Estádio do Maracanã": "马拉卡纳体育场",
    "Estádio do Pacaembu": "帕卡恩布体育场",
    "Fisht Stadium": "菲什特奥林匹克体育场",
    "Foxboro Stadium": "福克斯伯勒体育场",
    "Frankenstadion": "法兰克人体育场",
    "Free State Stadium": "自由州体育场",
    "Fritz-Walter-Stadion": "弗里茨·瓦尔特体育场",
    "Giants Stadium": "巨人体育场",
    "Goodison Park": "古迪逊公园球场",
    "Gottlieb-Daimler-Stadion": "戈特利布·戴姆勒体育场",
    "Gwangju World Cup Stadium": "光州世界杯体育场",
    "Hillsborough Stadium": "希尔斯堡球场",
    "Incheon Munhak Stadium": "仁川文鹤体育场",
    "International Stadium Yokohama": "横滨国际综合竞技场",
    "Jeju World Cup Stadium": "济州世界杯体育场",
    "Jeonju World Cup Stadium": "全州世界杯体育场",
    "Kaliningrad Stadium": "加里宁格勒体育场",
    "Kashima Soccer Stadium": "鹿岛足球场",
    "Kazan Arena": "喀山竞技场",
    "Khalifa International Stadium": "哈利法国际体育场",
    "Kobe Wing Stadium": "神户翼体育场",
    "Loftus Versfeld Stadium": "洛夫托斯球场",
    "Lusail Iconic Stadium": "卢赛尔地标体育场",
    "Luzhniki Stadium": "卢日尼基体育场",
    "Mbombela Stadium": "姆博贝拉体育场",
    "Miyagi Stadium": "宫城体育场",
    "Mordovia Arena": "莫尔多瓦竞技场",
    "Moses Mabhida Stadium": "摩西·马布海达体育场",
    "Munsu Cup Stadium": "蔚山文殊世界杯体育场",
    "Nagai Stadium": "长居体育场",
    "Neckarstadion": "内卡体育场",
    "Nelson Mandela Bay Stadium": "纳尔逊·曼德拉湾体育场",
    "Niedersachsenstadion": "下萨克森体育场",
    "Nizhny Novgorod Stadium": "下诺夫哥罗德体育场",
    "Old Trafford": "老特拉福德球场",
    "Olympiastadion": "奥林匹克体育场",
    "Parc Lescure": "莱斯屈尔公园球场",
    "Parc des Princes": "王子公园球场",
    "Parkstadion": "公园体育场",
    "Peter Mokaba Stadium": "彼得·莫卡巴体育场",
    "Pontiac Silverdome": "庞蒂亚克银顶体育场",
    "RFK Stadium": "罗伯特·肯尼迪纪念体育场",
    "RheinEnergieStadion": "莱茵能源体育场",
    "Rheinstadion": "莱茵体育场",
    "Roker Park": "罗克公园球场",
    "Rose Bowl": "玫瑰碗球场",
    "Rostov Arena": "罗斯托夫竞技场",
    "Royal Bafokeng Stadium": "皇家巴福肯体育场",
    "Råsunda Stadium": "拉松达体育场",
    "Saint Petersburg Stadium": "圣彼得堡体育场",
    "Saitama Stadium": "埼玉体育场",
    "Samara Arena": "萨马拉竞技场",
    "San Siro": "圣西罗球场",
    "Sapporo Dome": "札幌巨蛋",
    "Seoul World Cup Stadium": "首尔世界杯体育场",
    "Shizuoka Stadium": "静冈体育场",
    "Signal Iduna Park": "西格纳伊度纳公园球场",
    "Soccer City": "足球城体育场",
    "Soldier Field": "士兵球场",
    "Spartak Stadium": "斯巴达克体育场",
    "St. Jakob Stadium": "圣雅各布公园球场",
    "Stade Félix Bollaert": "费利克斯·博拉尔球场",
    "Stade Geoffroy-Guichard": "若弗鲁瓦·吉夏尔球场",
    "Stade Gerland": "热尔兰球场",
    "Stade Olympique de Colombes": "科隆布奥林匹克体育场",
    "Stade Vélodrome": "韦洛德罗姆球场",
    "Stade de France": "法兰西体育场",
    "Stade de Toulouse": "图卢兹体育场",
    "Stade de la Beaujoire": "博茹瓦尔球场",
    "Stade de la Meinau": "梅诺球场",
    "Stade de la Mosson": "莫松球场",
    "Stadio Artemio Franchi": "阿尔特米奥·弗兰基球场",
    "Stadio Comunale": "市政球场",
    "Stadio Delle Alpi": "阿尔卑球场",
    "Stadio Friuli": "弗留利球场",
    "Stadio La Favorita": "法沃里塔球场",
    "Stadio Luigi Ferraris": "路易吉·费拉里斯球场",
    "Stadio Marc'Antonio Bentegodi": "马尔坎托尼奥·本特戈蒂球场",
    "Stadio Nazionale PNF": "国家法西斯党体育场",
    "Stadio Olimpico": "罗马奥林匹克体育场",
    "Stadio Renato Dall'Ara": "雷纳托·达拉拉球场",
    "Stadio San Nicola": "圣尼古拉球场",
    "Stadio San Paolo": "圣保罗球场",
    "Stadio San Siro": "圣西罗球场",
    "Stadio Sant'Elia": "圣埃利亚球场",
    "Stadio delle Alpi": "阿尔卑球场",
    "Stadium 974": "974体育场",
    "Stanford Stadium": "斯坦福体育场",
    "Suwon World Cup Stadium": "水原世界杯体育场",
    "Ullevi": "乌勒维球场",
    "Veltins-Arena": "费尔廷斯竞技场",
    "Villa Park": "维拉公园球场",
    "Volgograd Arena": "伏尔加格勒竞技场",
    "Volksparkstadion": "人民公园体育场",
    "Waldstadion": "森林体育场",
    "Wankdorf Stadium": "万克多夫球场",
    "Wembley Stadium": "温布利球场",
    "Westfalenstadion": "威斯特法伦体育场",
    "White City Stadium": "白城体育场",
    "Zentralstadion": "中央体育场",
}

_VENUE_ZH.update({
    "Arosvallen": "阿罗斯瓦伦球场",
    "Asiad Main Stadium": "亚运会主体育场",
    "Balaídos": "巴莱多斯球场",
    "Charmilles Stadium": "沙米耶体育场",
    "Cornaredo Stadium": "科尔纳雷多体育场",
    "El Molinón": "莫利农球场",
    "Estadio Benito Villamarín": "贝尼托·比利亚马林球场",
    "Estadio Carlos Dittborn": "卡洛斯·迪特伯恩体育场",
    "Estadio Carlos Tartiere": "卡洛斯·塔尔蒂耶雷球场",
    "Estadio Chateau Carreras": "查托卡雷拉斯体育场",
    "Estadio Ciudad de Mendoza": "门多萨城市体育场",
    "Estadio Cuauhtémoc": "库奥特莫克体育场",
    "Estadio El Teniente": "埃尔特尼恩特体育场",
    "Estadio Gigante de Arroyito": "阿罗伊托巨人体育场",
    "Estadio José Amalfitani": "何塞·阿马尔菲塔尼体育场",
    "Estadio José Maria Minella": "何塞·玛丽亚·米内利亚体育场",
    "Estadio José María Minella": "何塞·玛丽亚·米内利亚体育场",
    "Estadio José Rico Pérez": "何塞·里科·佩雷斯体育场",
    "Estadio José Zorrilla": "何塞·索里利亚球场",
    "Estadio La Corregidora": "拉科雷希多拉体育场",
    "Estadio La Rosaleda": "玫瑰园球场",
    "Estadio Luis Casanova": "路易斯·卡萨诺瓦球场",
    "Estadio Luis Dosal": "路易斯·多萨尔体育场",
    "Estadio Nemesio Díez": "内梅西奥·迭斯体育场",
    "Estadio Neza 86": "内萨86体育场",
    "Estadio Nou Camp": "莱昂诺坎普球场",
    "Estadio Olímpico Chateau Carreras": "查托卡雷拉斯奥林匹克体育场",
    "Estadio Pocitos": "波西托斯体育场",
    "Estadio Ramón Sánchez Pizjuán": "拉蒙·桑切斯·皮斯胡安球场",
    "Estadio San Mamés": "圣马梅斯球场",
    "Estadio Sarriá": "萨里亚球场",
    "Estadio Sausalito": "索萨利托体育场",
    "Estadio Sergio León Chavez": "塞尔希奥·莱昂·查韦斯体育场",
    "Estadio Tecnológico": "科技体育场",
    "Estadio Tres de Marzo": "三月三日体育场",
    "Estadio Universitario": "大学体育场",
    "Estadio Vicente Calderón": "比森特·卡尔德隆球场",
    "Estadio de Riazor": "里亚索球场",
    "Estádio Durival Britto": "杜里瓦尔·布里托体育场",
    "Estádio Durival de Britto": "杜里瓦尔·德布里托体育场",
    "Estádio Ilha do Retiro": "雷蒂罗岛体育场",
    "Estádio Independência": "独立体育场",
    "Estádio dos Eucaliptos": "桉树林体育场",
    "Eyravallen": "埃拉瓦伦球场",
    "Hardturm Stadium": "哈德图姆体育场",
    "Idrottsparken": "伊德罗茨帕肯球场",
    "Jernvallen": "耶恩瓦伦球场",
    "La Romareda": "拉罗马雷达球场",
    "Malmö Stadion": "马尔默体育场",
    "Niigata Stadium": "新潟体育场",
    "Nuevo Estadio": "新体育场",
    "Rimnersvallen": "里姆纳斯瓦伦球场",
    "Ryavallen": "吕亚瓦伦球场",
    "Stade Chapou": "沙普球场",
    "Stade Olympique de la Pontaise": "蓬泰斯奥林匹克体育场",
    "Stade Victor Boucquey": "维克托·布凯球场",
    "Stade du Fort Carré": "卡雷堡体育场",
    "Stade municipal": "市政体育场",
    "Stadio Benito Mussolini": "贝尼托·墨索里尼体育场",
    "Stadio Giorgio Ascarelli": "乔治·阿斯卡雷利球场",
    "Stadio Giovanni Berta": "乔瓦尼·贝尔塔体育场",
    "Stadio Littoriale": "利托里亚莱球场",
    "Stadio Littorio": "利托里奥体育场",
    "Tunavallen": "图纳瓦伦球场",
    "Vélodrome Municipal": "市政自行车场体育场",
    "Örjans Vall": "厄尔扬斯瓦尔球场",
    "Ōita Stadium": "大分体育场",
})