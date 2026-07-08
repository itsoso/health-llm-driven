import api from './api';
import type { DailyArtifact } from './dailyArtifact';
import type { DailyOperatingPlan, DailyPlanAction } from './dailyPlan';
import type { TodayTimelineResponse } from './todayTimeline';
import type { GarminDailyRow } from '../types/garmin';
import { garminSleepHours } from '../types/garmin';

export interface MorningBriefingSection {
  title?: string | null;
  status?: string | null;
  items?: string[] | null;
}

export interface MorningBriefing {
  date?: string | null;
  greeting?: string | null;
  sections?: MorningBriefingSection[] | null;
}

export interface WeatherInner {
  available?: boolean;
  temperature?: number | null;
  weather?: string | null;
  humidity?: number | null;
}

export interface WeatherResponse {
  weather?: WeatherInner | null;
  exercise_advice?: string | null;
}

export interface AirQuality {
  available?: boolean;
  aqi?: number | null;
  aqi_description?: string | null;
  category?: string | null;
  description?: string | null;
  level?: string | null;
  pm25?: number | null;
  primary_pollutant?: string | null;
  advice_general?: string | null;
  health_effect?: string | null;
}

export type TodayBriefingRowId = 'weather' | 'air' | 'plan' | 'advice' | 'yesterday';

export interface TodayBriefingRow {
  id: TodayBriefingRowId;
  label: string;
  value: string;
  detail?: string | null;
  icon: string;
}

export interface TodayBriefingOverviewInput {
  morningBriefing?: MorningBriefing | null;
  weatherResponse?: WeatherResponse | null;
  airQuality?: AirQuality | null;
  dailyPlan?: DailyOperatingPlan | null;
  dailyArtifact?: DailyArtifact | null;
  timeline?: TodayTimelineResponse | null;
  recentGarminDaily?: GarminDailyRow[] | null;
}

export async function getTodayMorningBriefing(): Promise<MorningBriefing> {
  const { data } = await api.get<MorningBriefing>('/ai-scheduler/morning-briefing');
  return data;
}

export function buildTodayBriefingOverview(input: TodayBriefingOverviewInput): TodayBriefingRow[] {
  return [
    buildWeatherRow(input.weatherResponse),
    buildAirQualityRow(input.airQuality),
    buildPlanRow(input.dailyPlan, input.morningBriefing, input.timeline),
    buildAdviceRow(input.dailyArtifact, input.dailyPlan, input.morningBriefing),
    buildYesterdayRow(input.morningBriefing, input.recentGarminDaily),
  ];
}

function buildWeatherRow(weatherResponse?: WeatherResponse | null): TodayBriefingRow {
  const weather = weatherResponse?.weather;
  const pieces: string[] = [];
  if (typeof weather?.temperature === 'number') pieces.push(`${Math.round(weather.temperature)}°`);
  const weatherText = localizeWeatherText(weather?.weather);
  if (weatherText) pieces.push(weatherText);
  if (typeof weather?.humidity === 'number') pieces.push(`湿度 ${Math.round(weather.humidity)}%`);

  return {
    id: 'weather',
    label: '天气',
    icon: 'partly-sunny-outline',
    value: pieces.length > 0 ? pieces.join(' · ') : '天气待同步',
    detail: localizeEnvironmentAdvice(weatherResponse?.exercise_advice) || '用于安排户外、通勤和训练强度',
  };
}

function buildAirQualityRow(airQuality?: AirQuality | null): TodayBriefingRow {
  const aqi = typeof airQuality?.aqi === 'number' ? Math.round(airQuality.aqi) : null;
  const description = localizeAirQualityText(
    airQuality?.aqi_description ||
    airQuality?.category ||
    airQuality?.description ||
    airQuality?.level,
    aqi,
  );
  const value = aqi != null
    ? `AQI ${aqi}${description ? ` · ${description}` : ''}`
    : description || '空气质量待同步';

  const detail = [
    typeof airQuality?.pm25 === 'number' ? `PM2.5 ${Math.round(airQuality.pm25)}` : null,
    cleanText(airQuality?.primary_pollutant) ? `首要污染物 ${cleanText(airQuality?.primary_pollutant)}` : null,
    localizeEnvironmentAdvice(airQuality?.advice_general || airQuality?.health_effect),
  ].filter(Boolean).join(' · ');

  return {
    id: 'air',
    label: '空气质量',
    icon: 'leaf-outline',
    value,
    detail: detail || '用于判断户外活动和通风策略',
  };
}

function buildPlanRow(
  dailyPlan?: DailyOperatingPlan | null,
  morningBriefing?: MorningBriefing | null,
  timeline?: TodayTimelineResponse | null,
): TodayBriefingRow {
  const actions = planActions(dailyPlan);
  const morningGoals = findMorningSection(morningBriefing, /目标|提醒|计划/);
  const primaryGoal = localizePlanGoal(dailyPlan?.primary_goal);
  const firstAction = actions[0];
  const timelineCount = Math.max(0, Math.round(timeline?.counts?.actionable ?? 0));
  const value = primaryGoal || cleanText(firstAction?.title) || firstItem(morningGoals) || '今日规划待生成';
  const actionDetail = actions
    .slice(0, 2)
    .map(action => cleanText(action.title))
    .filter(Boolean)
    .join(' · ');
  const morningDetail = listItems(morningGoals).slice(0, 3).join(' · ');

  return {
    id: 'plan',
    label: '今日规划',
    icon: 'calendar-outline',
    value,
    detail: actionDetail || morningDetail || (timelineCount > 0 ? `${timelineCount} 项待办` : '暂无明确待办'),
  };
}

function buildAdviceRow(
  dailyArtifact?: DailyArtifact | null,
  dailyPlan?: DailyOperatingPlan | null,
  morningBriefing?: MorningBriefing | null,
): TodayBriefingRow {
  const topAction = dailyArtifact?.top_action;
  if (topAction?.title) {
    return {
      id: 'advice',
      label: '建议',
      icon: 'sparkles-outline',
      value: cleanText(topAction.title) || '暂无新的行动建议',
      detail: cleanText(topAction.do_now || topAction.why_now || dailyArtifact?.state?.summary),
    };
  }

  const firstPlanAction = planActions(dailyPlan)[0];
  if (firstPlanAction?.title) {
    return {
      id: 'advice',
      label: '建议',
      icon: 'sparkles-outline',
      value: cleanText(firstPlanAction.title) || '暂无新的行动建议',
      detail: cleanText(firstPlanAction.why),
    };
  }

  const reminders = findMorningSection(morningBriefing, /提醒|建议/);
  const reminderItems = listItems(reminders);
  return {
    id: 'advice',
    label: '建议',
    icon: 'sparkles-outline',
    value: reminderItems[0] || '暂无新的行动建议',
    detail: reminderItems.slice(1, 3).join(' · ') || null,
  };
}

function buildYesterdayRow(
  morningBriefing?: MorningBriefing | null,
  recentGarminDaily?: GarminDailyRow[] | null,
): TodayBriefingRow {
  const sleepSection = findMorningSection(morningBriefing, /昨晚|昨日|睡眠/);
  const bodySection = findMorningSection(morningBriefing, /身体状态|恢复|压力|HRV/i);
  const sleepItems = listItems(sleepSection);
  const bodyItems = listItems(bodySection);
  if (sleepItems.length > 0 || bodyItems.length > 0) {
    return {
      id: 'yesterday',
      label: '昨日总结',
      icon: 'moon-outline',
      value: sleepItems[0] || bodyItems[0] || '昨日数据待同步',
      detail: [...sleepItems.slice(1), ...bodyItems].slice(0, 4).join(' · ') || null,
    };
  }

  const garmin = pickLatestHistoricalGarmin(recentGarminDaily);
  if (garmin) {
    const sleepHours = garminSleepHours(garmin);
    const value = typeof garmin.sleep_score === 'number'
      ? `睡眠 ${Math.round(garmin.sleep_score)} 分`
      : sleepHours != null
        ? `睡眠 ${sleepHours.toFixed(1)} 小时`
        : typeof garmin.steps === 'number'
          ? `步数 ${formatInt(garmin.steps)}`
          : '昨日数据待同步';
    const detail = [
      sleepHours != null && !value.includes('小时') ? `睡眠 ${sleepHours.toFixed(1)} 小时` : null,
      typeof garmin.steps === 'number' && !value.includes('步数') ? `步数 ${formatInt(garmin.steps)}` : null,
      typeof garmin.hrv === 'number' ? `HRV ${Math.round(garmin.hrv)}ms` : null,
      typeof garmin.body_battery_most_charged === 'number' ? `身体电量 ${Math.round(garmin.body_battery_most_charged)}` : null,
    ].filter(Boolean).join(' · ');

    return {
      id: 'yesterday',
      label: '昨日总结',
      icon: 'moon-outline',
      value,
      detail: detail || null,
    };
  }

  return {
    id: 'yesterday',
    label: '昨日总结',
    icon: 'moon-outline',
    value: '昨日数据待同步',
    detail: '等待 Garmin / 睡眠 / 打卡数据更新',
  };
}

function planActions(dailyPlan?: DailyOperatingPlan | null): DailyPlanAction[] {
  return Array.isArray(dailyPlan?.actions)
    ? dailyPlan.actions.filter(action => Boolean(cleanText(action?.title)))
    : [];
}

function findMorningSection(
  morningBriefing: MorningBriefing | null | undefined,
  pattern: RegExp,
): MorningBriefingSection | null {
  return (morningBriefing?.sections ?? []).find(section => pattern.test(cleanText(section?.title))) ?? null;
}

function listItems(section?: MorningBriefingSection | null): string[] {
  return Array.isArray(section?.items)
    ? section.items.map(cleanText).filter(Boolean)
    : [];
}

function firstItem(section?: MorningBriefingSection | null): string {
  return listItems(section)[0] || '';
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function localizeWeatherText(value: unknown): string {
  const text = cleanText(value);
  if (!text) return '';
  if (hasCjk(text)) return text;
  const key = text.toLowerCase();
  const exact: Record<string, string> = {
    clear: '晴',
    sunny: '晴',
    cloudy: '多云',
    clouds: '多云',
    overcast: '阴',
    'partly cloudy': '多云',
    rain: '雨',
    rainy: '雨',
    snow: '雪',
    fog: '雾',
    mist: '雾',
    haze: '霾',
    thunderstorm: '雷阵雨',
    windy: '有风',
  };
  if (exact[key]) return exact[key];
  if (key.includes('cloud')) return '多云';
  if (key.includes('clear') || key.includes('sun')) return '晴';
  if (key.includes('rain') || key.includes('shower')) return '雨';
  if (key.includes('snow')) return '雪';
  if (key.includes('fog') || key.includes('mist')) return '雾';
  if (key.includes('haze') || key.includes('smog')) return '霾';
  if (key.includes('thunder') || key.includes('storm')) return '雷阵雨';
  if (key.includes('wind')) return '有风';
  return '天气已同步';
}

function localizeAirQualityText(value: unknown, aqi?: number | null): string {
  const text = cleanText(value);
  if (text && hasCjk(text)) return text;
  const key = text.toLowerCase();
  const exact: Record<string, string> = {
    excellent: '优',
    good: '良',
    moderate: '中等',
    fair: '良',
    unhealthy: '不健康',
    'unhealthy for sensitive groups': '对敏感人群不健康',
    'very unhealthy': '非常不健康',
    hazardous: '危险',
  };
  if (exact[key]) return exact[key];
  if (key.includes('excellent')) return '优';
  if (key.includes('good')) return '良';
  if (key.includes('moderate')) return '中等';
  if (key.includes('sensitive')) return '对敏感人群不健康';
  if (key.includes('very unhealthy')) return '非常不健康';
  if (key.includes('unhealthy')) return '不健康';
  if (key.includes('hazard')) return '危险';
  if (typeof aqi === 'number') return airQualityCategoryByAqi(aqi);
  return '';
}

function airQualityCategoryByAqi(aqi: number): string {
  if (aqi <= 50) return '优';
  if (aqi <= 100) return '良';
  if (aqi <= 150) return '轻度污染';
  if (aqi <= 200) return '中度污染';
  if (aqi <= 300) return '重度污染';
  return '严重污染';
}

function localizeEnvironmentAdvice(value: unknown): string {
  const text = cleanText(value);
  if (!text) return '';
  if (hasCjk(text)) return text;
  const key = text.toLowerCase();
  if (key.includes('outdoor') || key.includes('activit')) return '适合户外活动';
  if (key.includes('ventilat')) return '可适度通风';
  if (key.includes('mask')) return '外出建议佩戴口罩';
  if (key.includes('limit') || key.includes('avoid')) return '减少长时间户外活动';
  return '';
}

function localizePlanGoal(value: unknown): string {
  const text = cleanText(value);
  if (!text) return '';
  if (hasCjk(text)) return text;
  const key = text.toLowerCase();
  const exact: Record<string, string> = {
    metabolic_health: '代谢健康',
    metabolism: '代谢健康',
    weight_loss: '体重管理',
    body_composition: '体成分管理',
    cardiovascular: '心血管健康',
    cardio_fitness: '心肺体能',
    sleep: '睡眠恢复',
    sleep_recovery: '睡眠恢复',
    recovery: '恢复',
    movement: '活动',
    nutrition: '营养',
    hydration: '补水',
    medication_safety: '用药安全',
    disease_risk: '疾病风险管理',
  };
  if (exact[key]) return exact[key];
  if (/^[a-z0-9_ -]+$/i.test(text)) return '今日健康目标';
  return text;
}

function hasCjk(value: string): boolean {
  return /[\u3400-\u9fff]/u.test(value);
}

function pickLatestHistoricalGarmin(rows?: GarminDailyRow[] | null): GarminDailyRow | null {
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const today = localIsoDate();
  const candidates = rows
    .filter(row => typeof row.record_date === 'string' && row.record_date < today)
    .sort((a, b) => String(b.record_date).localeCompare(String(a.record_date)));
  return candidates[0] ?? null;
}

function localIsoDate(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function formatInt(value: number): string {
  return Math.round(value).toLocaleString('zh-CN');
}
