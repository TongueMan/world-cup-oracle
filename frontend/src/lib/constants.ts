const TEAM_NAMES: Record<string, string> = {
  BRA: '巴西',
  ARG: '阿根廷',
  MEX: '墨西哥',
  JPN: '日本',
  FRA: '法国',
  ENG: '英格兰',
  USA: '美国',
  KOR: '韩国',
  GER: '德国',
  ESP: '西班牙',
  MAR: '摩洛哥',
  AUS: '澳大利亚',
  POR: '葡萄牙',
  NED: '荷兰',
  SEN: '塞内加尔',
  ECU: '厄瓜多尔',
  BEL: '比利时',
  ITA: '意大利',
  URU: '乌拉圭',
  COL: '哥伦比亚',
  CRO: '克罗地亚',
  SUI: '瑞士',
  DEN: '丹麦',
  AUT: '奥地利',
  IRN: '伊朗',
  SRB: '塞尔维亚',
  SWE: '瑞典',
  UKR: '乌克兰',
  POL: '波兰',
  CAN: '加拿大',
  TUR: '土耳其',
  NOR: '挪威',
  NGA: '尼日利亚',
  EGY: '埃及',
  ALG: '阿尔及利亚',
  TUN: '突尼斯',
  CMR: '喀麦隆',
  GHA: '加纳',
  QAT: '卡塔尔',
  KSA: '沙特阿拉伯',
  UAE: '阿联酋',
  CHN: '中国',
  NZL: '新西兰',
  CRC: '哥斯达黎加',
  PAN: '巴拿马',
  JAM: '牙买加',
  PAR: '巴拉圭',
  CHI: '智利',
  PER: '秘鲁',
  RSA: '南非',
  CIV: '科特迪瓦',
  MLI: '马里',
  VEN: '委内瑞拉',
  BOL: '玻利维亚',
};

export function getTeamName(teamId: string | null | undefined): string {
  if (!teamId) return '待定';
  return TEAM_NAMES[teamId] ?? teamId;
}

const ROUND_LABELS: Record<string, string> = {
  R32: '三十二强',
  R16: '十六强',
  QF: '四分之一决赛',
  SF: '半决赛',
  ThirdPlace: '三四名决赛',
  Final: '决赛',
};

export function getRoundLabel(round: string): string {
  return ROUND_LABELS[round] ?? round;
}
