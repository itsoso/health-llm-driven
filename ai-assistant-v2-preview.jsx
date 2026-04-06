import { useState, useEffect, useMemo } from "react";

// ============================================================================
// Mock Data — 模拟真实 API 数据
// ============================================================================
const MOCK = {
  user: { name: "baokun" },
  healthScore: {
    total_score: 57,
    grade: "需要关注",
    dimensions: { exercise: 20, sleep: 78, diet: 35, vitals: 72, weight: 65, hydration: 12 },
  },
  dailyInsight: "昨夜睡眠质量不错（89分），但HRV偏低（68ms），建议今天以低强度恢复为主。饮水量严重不足，请尽快补水。",
  garmin: {
    resting_heart_rate: 49,
    avg_heart_rate: 62,
    body_battery_high: 85,
    body_battery_low: 42,
    body_battery_current: 58,
    sleep_score: 89,
    total_sleep_duration: 467,
    deep_sleep_duration: 102,
    rem_sleep_duration: 88,
    light_sleep_duration: 277,
    stress_level: 16,
    hrv: 68,
    hrv_7day_avg: 62,
    steps: 255,
    active_calories: 45,
    calories_burned: 1680,
    spo2: 97,
  },
  weather: { city: "杭州", temperature: 26, weather_description: "多云", temp_min: 17, temp_max: 28, humidity: 65 },
  air: { aqi: 52, pm25: 16.67, quality: "良" },
  water: { total_ml: 0, goal_ml: 2000, count: 0 },
  diet: { total_calories: 0, total_protein: 0, total_carbs: 0, total_fat: 0, meals_count: 0 },
  rhinitis: { sneeze_count: 0, nasal_wash_count: 0 },
  weight: { current_weight: 76, weight_change: -1.2, bmi: 23.8 },
  supplements: [
    { name: "维生素D3", dosage: "5000IU", timing: "morning", taken: false },
    { name: "鱼肝油", dosage: "5000IU", timing: "morning", taken: false },
    { name: "甘氨酸镁", dosage: "", timing: "morning", taken: false },
    { name: "复合维生素B", dosage: "", timing: "morning", taken: false },
    { name: "甘氨酸锌", dosage: "30mg", timing: "morning", taken: false },
    { name: "NAC", dosage: "2粒", timing: "morning", taken: false },
    { name: "辅酶Q10", dosage: "100mg", timing: "noon", taken: false },
    { name: "叶黄素", dosage: "20mg", timing: "noon", taken: false },
    { name: "褪黑素", dosage: "3mg", timing: "bedtime", taken: false },
    { name: "甘氨酸", dosage: "3g", timing: "bedtime", taken: false },
    { name: "镁", dosage: "400mg", timing: "bedtime", taken: false },
    { name: "益生菌", dosage: "1包", timing: "evening", taken: false },
  ],
  garminHistory: [
    { date: "03-30", hr: 52, hrv: 58, stress: 22, steps: 8200, sleep: 82 },
    { date: "03-31", hr: 48, hrv: 65, stress: 18, steps: 6500, sleep: 85 },
    { date: "04-01", hr: 51, hrv: 62, stress: 25, steps: 9100, sleep: 79 },
    { date: "04-02", hr: 49, hrv: 55, stress: 20, steps: 7300, sleep: 88 },
    { date: "04-03", hr: 47, hrv: 70, stress: 15, steps: 10200, sleep: 91 },
    { date: "04-04", hr: 50, hrv: 64, stress: 19, steps: 5800, sleep: 86 },
    { date: "04-05", hr: 49, hrv: 68, stress: 16, steps: 255, sleep: 89 },
  ],
  prevHistory: [
    { hr: 54, hrv: 52, stress: 28, steps: 7100 },
    { hr: 52, hrv: 48, stress: 30, steps: 6200 },
    { hr: 55, hrv: 50, stress: 26, steps: 8400 },
    { hr: 53, hrv: 55, stress: 24, steps: 7800 },
    { hr: 51, hrv: 58, stress: 22, steps: 9000 },
    { hr: 50, hrv: 54, stress: 25, steps: 6900 },
    { hr: 52, hrv: 56, stress: 23, steps: 7500 },
  ],
  workouts: [
    { name: "晨跑", type: "running", distance: 5.2, duration: 32, calories: 320, hr: 145, date: "04-03", pace: "6:09" },
    { name: "力量训练", type: "strength", distance: 0, duration: 45, calories: 280, hr: 128, date: "04-01" },
    { name: "骑行", type: "cycling", distance: 18.5, duration: 55, calories: 410, hr: 135, date: "03-29" },
  ],
  goals: [
    { title: "每周跑步3次", current: 2, target: 3, unit: "次", type: "exercise" },
    { title: "每日步数8000", current: 255, target: 8000, unit: "步", type: "steps" },
    { title: "体重降至74kg", current: 76, target: 74, unit: "kg", type: "weight" },
    { title: "每日饮水2000ml", current: 0, target: 2000, unit: "ml", type: "hydration" },
  ],
  mood: { score: 7, energy: 6, stress: 3, anxiety: 2, tags: ["平静", "专注", "有动力"], journal: "今天状态不错" },
  bloodPressure: { systolic: 118, diastolic: 75, pulse: 62, date: "04-04" },
  bodyComp: { body_fat: 18.5, muscle_mass: 32.1, visceral_fat: 8 },
};

// ============================================================================
// SVG 图表组件
// ============================================================================

function AnimatedRing({ score, size = 88, strokeWidth = 7 }) {
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const [offset, setOffset] = useState(c);
  const target = c - (score / 100) * c;
  useEffect(() => { const t = setTimeout(() => setOffset(target), 100); return () => clearTimeout(t); }, [score, target]);
  const color = score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e5e7eb" strokeWidth={strokeWidth} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
    </svg>
  );
}

function ProgressRing({ pct, color, size = 64, sw = 5, label, display, sub }) {
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const [offset, setOffset] = useState(c);
  useEffect(() => { const t = setTimeout(() => setOffset(c - (pct / 100) * c), 100); return () => clearTimeout(t); }, [pct, c]);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={sw} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={sw}
            strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 1s ease" }} />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: "#374151" }}>{pct}%</span>
        </div>
      </div>
      <span style={{ fontSize: 14, fontWeight: 600, color: "#374151", marginTop: 8 }}>{display}</span>
      {sub && <span style={{ fontSize: 11, color: "#9ca3af" }}>{sub}</span>}
      <span style={{ fontSize: 11, color: "#9ca3af" }}>{label}</span>
    </div>
  );
}

function Sparkline({ data, color = "#22c55e", w = 140, h = 36 }) {
  if (!data.length) return null;
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`).join(" ");
  const gid = "g" + color.replace("#", "");
  return (
    <svg width={w} height={h} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon fill={`url(#${gid})`} points={`0,${h} ${pts} ${w},${h}`} />
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}

function SleepBar({ deep, rem, light }) {
  const t = deep + rem + light;
  if (t <= 0) return null;
  return (
    <div style={{ display: "flex", height: 12, borderRadius: 8, overflow: "hidden", background: "#f3f4f6" }}>
      <div style={{ width: `${(deep / t) * 100}%`, background: "#1e3a5f", transition: "width 1s", borderRadius: "8px 0 0 8px" }} />
      <div style={{ width: `${(rem / t) * 100}%`, background: "#6366f1", transition: "width 1s" }} />
      <div style={{ width: `${(light / t) * 100}%`, background: "#c7d2fe", transition: "width 1s", borderRadius: "0 8px 8px 0" }} />
    </div>
  );
}

// ============================================================================
// 主面板样式常量
// ============================================================================
const FONT = '-apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

const card = {
  background: "#fff",
  borderRadius: 16,
  border: "1px solid #f0f0f0",
  padding: 20,
  boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
};

const sectionTitle = (icon, text, right) => (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontSize: 15 }}>{icon}</span>
      <span style={{ fontSize: 14, fontWeight: 600, color: "#1f2937" }}>{text}</span>
    </div>
    {right}
  </div>
);

// ============================================================================
// 主组件
// ============================================================================
export default function AIAssistantV2() {
  const [suppExpanded, setSuppExpanded] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [inputValue, setInputValue] = useState("");

  const g = MOCK.garmin;
  const hour = new Date().getHours();
  const greeting = hour < 6 ? "夜深了" : hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";

  // 睡眠数据
  const sleepTotal = g.total_sleep_duration / 60;
  const sleepH = Math.floor(sleepTotal);
  const sleepM = Math.round((sleepTotal - sleepH) * 60);
  const sleepDeep = g.deep_sleep_duration / 60;
  const sleepRem = g.rem_sleep_duration / 60;
  const sleepLight = g.light_sleep_duration / 60;

  // 趋势计算
  const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const pctChange = (cur, prev) => prev > 0 ? ((cur - prev) / prev * 100).toFixed(1) : "0";
  const last7 = MOCK.garminHistory;
  const prev7 = MOCK.prevHistory;

  // 智能警报
  const alerts = useMemo(() => {
    const list = [];
    if (hour >= 7 && MOCK.water.total_ml < 300) {
      list.push({ icon: "💧", text: `已${hour}点，饮水仅 ${MOCK.water.total_ml}ml，需要补充`, color: "#ef4444", bg: "#fef2f2" });
    }
    const suppRemaining = MOCK.supplements.filter(s => !s.taken).length;
    if (suppRemaining > 0 && hour >= 7) {
      list.push({ icon: "💊", text: `${suppRemaining}项补剂待服用`, color: "#8b5cf6", bg: "#f5f3ff" });
    }
    if (hour >= 14 && g.steps < 3000) {
      list.push({ icon: "🚶", text: `步数仅 ${g.steps}，活动量偏低`, color: "#f59e0b", bg: "#fffbeb" });
    }
    if (g.hrv && g.hrv < 40) {
      list.push({ icon: "💓", text: `HRV ${g.hrv}ms 偏低`, color: "#ef4444", bg: "#fef2f2" });
    }
    return list;
  }, []);

  // 进度百分比
  const stepsPct = Math.min(100, Math.round((g.steps / 8000) * 100));
  const waterPct = Math.min(100, Math.round((MOCK.water.total_ml / MOCK.water.goal_ml) * 100));
  const suppChecked = MOCK.supplements.filter(s => s.taken).length;
  const suppTotal = MOCK.supplements.length;
  const suppPct = suppTotal > 0 ? Math.round((suppChecked / suppTotal) * 100) : 0;

  const timingLabels = { morning: "早晨", noon: "中午", evening: "晚上", bedtime: "睡前" };
  const suppGrouped = {};
  MOCK.supplements.forEach(s => {
    if (!suppGrouped[s.timing]) suppGrouped[s.timing] = [];
    suppGrouped[s.timing].push(s);
  });
  const suppFlat = ["morning", "noon", "evening", "bedtime"].flatMap(t => (suppGrouped[t] || []).map(s => ({ ...s, _timing: t })));
  const suppVisible = suppExpanded ? suppFlat : suppFlat.slice(0, 6);

  const handleSend = (text) => {
    if (!text?.trim()) return;
    setChatMessages(prev => [...prev, { role: "user", content: text }]);
    setInputValue("");
  };

  const isWelcome = chatMessages.length === 0;

  const hs = MOCK.healthScore;
  const scoreColor = hs.total_score >= 80 ? "#22c55e" : hs.total_score >= 60 ? "#f59e0b" : "#ef4444";
  const dimNames = { exercise: "动", sleep: "眠", diet: "食", vitals: "征", weight: "重", hydration: "水" };

  return (
    <div style={{ fontFamily: FONT, background: "#f8fafb", minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <header style={{ position: "sticky", top: 0, zIndex: 50, backdropFilter: "blur(12px)", background: "rgba(255,255,255,0.85)", borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ maxWidth: 900, margin: "0 auto", padding: "0 24px", height: 56, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 10, background: "linear-gradient(135deg, #22c55e, #14b8a6)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 14, fontWeight: 700 }}>H</div>
            <span style={{ fontWeight: 600, color: "#1f2937", fontSize: 15 }}>智能助理</span>
            <span style={{ fontSize: 11, color: "#9ca3af", background: "#f3f4f6", padding: "2px 8px", borderRadius: 6 }}>V2</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button style={{ color: "#9ca3af", background: "none", border: "none", cursor: "pointer", fontSize: 13 }}>历史</button>
            <button style={{ color: "#9ca3af", background: "none", border: "none", cursor: "pointer", fontSize: 18, lineHeight: 1 }}>+</button>
            <div style={{ width: 32, height: 32, borderRadius: "50%", background: "linear-gradient(135deg, #22c55e, #059669)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 700 }}>
              {MOCK.user.name.charAt(0).toUpperCase()}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main style={{ flex: 1, overflow: "auto", padding: "24px 16px 120px" }}>
        <div style={{ maxWidth: 860, margin: "0 auto" }}>
          {isWelcome ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

              {/* ── 1. Status Header ── */}
              <div style={{ borderRadius: 20, padding: 24, background: "linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #334155 100%)", position: "relative", overflow: "hidden" }}>
                <div style={{ position: "absolute", top: -40, right: -40, width: 160, height: 160, borderRadius: "50%", background: `radial-gradient(circle, ${scoreColor}30, transparent)` }} />
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                  <h1 style={{ fontSize: 18, fontWeight: 700, color: "#fff", margin: 0 }}>{greeting}，{MOCK.user.name}</h1>
                  <button style={{ fontSize: 12, color: "rgba(255,255,255,0.4)", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    刷新
                  </button>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
                  <div style={{ position: "relative", flexShrink: 0 }}>
                    <AnimatedRing score={hs.total_score} />
                    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                      <span style={{ fontSize: 26, fontWeight: 700, color: "#fff" }}>{hs.total_score}</span>
                      <span style={{ fontSize: 10, color: "rgba(255,255,255,0.5)" }}>健康分</span>
                    </div>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: scoreColor }}>{hs.total_score >= 80 ? "状态优秀" : hs.total_score >= 60 ? "状态一般" : "需要关注"}</span>
                      {Object.entries(hs.dimensions).some(([, v]) => v < 40) && (() => {
                        const worst = Object.entries(hs.dimensions).reduce((a, b) => b[1] < a[1] ? b : a);
                        const names = { exercise: "运动", sleep: "睡眠", diet: "饮食", vitals: "体征", weight: "体重", hydration: "水分" };
                        return worst[1] < 40 ? (
                          <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 12, background: `${scoreColor}20`, color: scoreColor, fontWeight: 500 }}>
                            {names[worst[0]]} 偏低
                          </span>
                        ) : null;
                      })()}
                    </div>
                    <p style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, margin: 0, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                      {MOCK.dailyInsight}
                    </p>
                    {/* Dimension bars */}
                    <div style={{ display: "flex", gap: 4, marginTop: 12 }}>
                      {Object.entries(hs.dimensions).map(([k, v]) => {
                        const barColor = v >= 70 ? "#22c55e" : v >= 40 ? "#f59e0b" : "#ef4444";
                        return (
                          <div key={k} style={{ flex: 1 }}>
                            <div style={{ height: 4, borderRadius: 4, background: "rgba(255,255,255,0.1)", overflow: "hidden" }}>
                              <div style={{ height: "100%", borderRadius: 4, background: barColor, width: `${v}%`, transition: "width 0.8s" }} />
                            </div>
                            <div style={{ fontSize: 9, color: "rgba(255,255,255,0.3)", textAlign: "center", marginTop: 3 }}>{dimNames[k]}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>

              {/* ── 2. Smart Alerts ── */}
              {alerts.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {alerts.map((a, i) => (
                    <button key={i} style={{ width: "100%", borderRadius: 14, padding: "12px 16px", display: "flex", alignItems: "center", gap: 12, textAlign: "left", background: a.bg, border: `1px solid ${a.color}15`, cursor: "pointer", transition: "all 0.2s" }}
                      onMouseEnter={e => e.currentTarget.style.transform = "translateY(-1px)"}
                      onMouseLeave={e => e.currentTarget.style.transform = "none"}>
                      <span style={{ fontSize: 18 }}>{a.icon}</span>
                      <span style={{ flex: 1, fontSize: 14, fontWeight: 500, color: a.color }}>{a.text}</span>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke={a.color} strokeWidth="2"><path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    </button>
                  ))}
                </div>
              )}

              {/* ── 3. Body Snapshot ── */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                {[
                  { icon: "❤️", value: g.resting_heart_rate, unit: "bpm", label: "心率", sub: "", ok: v => v >= 45 && v <= 75 },
                  { icon: "🔋", value: g.body_battery_current, unit: "", label: "电量", sub: `峰值 ${g.body_battery_high}`, ok: v => v >= 50 },
                  { icon: "😴", value: g.sleep_score, unit: "分", label: "睡眠", sub: `${sleepH}h${sleepM}m`, ok: v => v >= 70 },
                  { icon: "😌", value: g.stress_level, unit: "", label: "压力", sub: g.spo2 ? `SpO2 ${g.spo2}%` : "", ok: v => v <= 40 },
                ].map(m => {
                  const isOk = m.value != null && m.ok(m.value);
                  const isWarn = m.value != null && !isOk;
                  return (
                    <div key={m.label} style={{ ...card, padding: 16, textAlign: "center", background: isWarn ? "#fffbeb" : "#fff" }}>
                      <span style={{ fontSize: 20 }}>{m.icon}</span>
                      <div style={{ fontSize: 28, fontWeight: 700, color: isWarn ? "#f59e0b" : "#1f2937", marginTop: 4 }}>
                        {m.value ?? "--"}
                        {m.unit && <span style={{ fontSize: 12, fontWeight: 400, color: "#9ca3af", marginLeft: 2 }}>{m.unit}</span>}
                      </div>
                      <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>{m.label}</div>
                      {m.sub && <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2 }}>{m.sub}</div>}
                    </div>
                  );
                })}
              </div>

              {/* ── 4. Life Context Grid ── */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                {/* Weather */}
                <div style={{ ...card, padding: 16, background: "linear-gradient(135deg, #eff6ff, #f0f9ff)", borderColor: "#dbeafe80" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#1f2937" }}>{MOCK.weather.city}</span>
                    <span style={{ fontSize: 12, color: "#6b7280" }}>{MOCK.weather.weather_description}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span style={{ fontSize: 32, fontWeight: 700, color: "#1f2937" }}>{MOCK.weather.temperature}°</span>
                    <span style={{ fontSize: 12, color: "#9ca3af" }}>{MOCK.weather.temp_min}° / {MOCK.weather.temp_max}°</span>
                  </div>
                  <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, fontWeight: 500, padding: "2px 6px", borderRadius: 4, background: MOCK.air.aqi <= 50 ? "#dcfce7" : "#fef9c3", color: MOCK.air.aqi <= 50 ? "#16a34a" : "#ca8a04" }}>AQI {MOCK.air.aqi}</span>
                    <span style={{ fontSize: 11, fontWeight: 500, padding: "2px 6px", borderRadius: 4, background: "#f0fdf4", color: "#16a34a" }}>PM2.5 {MOCK.air.pm25}</span>
                  </div>
                </div>

                {/* Diet */}
                <div style={{ ...card, padding: 16, background: "linear-gradient(135deg, #fff7ed, #fffbeb)", borderColor: "#fed7aa80" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#1f2937" }}>饮食</span>
                    <span style={{ fontSize: 11, color: "#9ca3af" }}>{MOCK.diet.meals_count}餐</span>
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: "#1f2937" }}>
                    {MOCK.diet.total_calories}<span style={{ fontSize: 12, fontWeight: 400, color: "#9ca3af", marginLeft: 2 }}>kcal</span>
                  </div>
                  <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                    <span style={{ fontSize: 11, color: "#6b7280" }}><span style={{ color: "#ef4444", fontWeight: 500 }}>{MOCK.diet.total_protein}</span>g 蛋白</span>
                    <span style={{ fontSize: 11, color: "#6b7280" }}><span style={{ color: "#f59e0b", fontWeight: 500 }}>{MOCK.diet.total_carbs}</span>g 碳水</span>
                    <span style={{ fontSize: 11, color: "#6b7280" }}><span style={{ color: "#22c55e", fontWeight: 500 }}>{MOCK.diet.total_fat}</span>g 脂肪</span>
                  </div>
                </div>

                {/* Rhinitis */}
                <div style={{ ...card, padding: 16, background: "linear-gradient(135deg, #faf5ff, #f5f3ff)", borderColor: "#e9d5ff80" }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginBottom: 8 }}>👃 鼻炎追踪</div>
                  <div style={{ display: "flex", gap: 20 }}>
                    <div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: "#1f2937" }}>{MOCK.rhinitis.sneeze_count}</div>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>喷嚏</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: "#1f2937" }}>{MOCK.rhinitis.nasal_wash_count}<span style={{ fontSize: 14, color: "#9ca3af" }}>/2</span></div>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>洗鼻</div>
                    </div>
                  </div>
                </div>

                {/* Weight */}
                <div style={{ ...card, padding: 16, background: "linear-gradient(135deg, #f0fdf4, #ecfdf5)", borderColor: "#bbf7d080" }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginBottom: 8 }}>⚖️ 体重</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: "#1f2937" }}>
                    {MOCK.weight.current_weight}<span style={{ fontSize: 12, fontWeight: 400, color: "#9ca3af", marginLeft: 2 }}>kg</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 500, color: MOCK.weight.weight_change < 0 ? "#16a34a" : "#ef4444" }}>
                      30天 {MOCK.weight.weight_change > 0 ? "+" : ""}{MOCK.weight.weight_change}kg
                    </span>
                    <span style={{ fontSize: 11, color: "#9ca3af" }}>BMI {MOCK.weight.bmi}</span>
                  </div>
                </div>
              </div>

              {/* ── 5. Progress Rings ── */}
              <div style={{ ...card }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24 }}>
                  <ProgressRing pct={stepsPct} color="#6366f1" label="步数" display={g.steps.toLocaleString()} sub="/8,000" />
                  <ProgressRing pct={waterPct} color="#3b82f6" label="饮水" display={`${MOCK.water.total_ml}`} sub={`/${MOCK.water.goal_ml}ml`} />
                  <ProgressRing pct={suppPct} color="#8b5cf6" label="补剂" display={`${suppChecked}/${suppTotal}`} sub="" />
                </div>
              </div>

              {/* ── 6. Sleep Detail ── */}
              <div style={{ ...card }}>
                {sectionTitle("🌙", "昨夜睡眠详情", <span style={{ fontSize: 12, color: "#9ca3af" }}>{sleepH}h{sleepM > 0 ? sleepM + "m" : ""}</span>)}
                <SleepBar deep={sleepDeep} rem={sleepRem} light={sleepLight} />
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, fontSize: 12, color: "#6b7280" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: "#1e3a5f" }} /> 深睡 {sleepDeep.toFixed(1)}h</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: "#6366f1" }} /> REM {sleepRem.toFixed(1)}h</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: "#c7d2fe" }} /> 浅睡 {sleepLight.toFixed(1)}h</span>
                </div>
                <div style={{ display: "flex", gap: 24, marginTop: 12, paddingTop: 12, borderTop: "1px solid #f3f4f6" }}>
                  <div><span style={{ fontSize: 26, fontWeight: 700, color: "#1f2937" }}>{g.sleep_score}</span><span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 4 }}>睡眠分</span></div>
                  <div><span style={{ fontSize: 20, fontWeight: 600, color: "#374151" }}>{g.hrv}</span><span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 4 }}>HRV ms</span></div>
                  <div><span style={{ fontSize: 20, fontWeight: 600, color: "#374151" }}>{g.resting_heart_rate}</span><span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 4 }}>静息心率</span></div>
                </div>
              </div>

              {/* ── 7. Blood Pressure & Body Composition ── */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div style={{ ...card }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginBottom: 8 }}>🩺 血压</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: "#1f2937" }}>
                    {MOCK.bloodPressure.systolic}/{MOCK.bloodPressure.diastolic}
                  </div>
                  <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>脉搏 {MOCK.bloodPressure.pulse} bpm</div>
                  <div style={{ fontSize: 11, color: "#d1d5db", marginTop: 4 }}>{MOCK.bloodPressure.date}</div>
                </div>
                <div style={{ ...card }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginBottom: 8 }}>📐 体成分</div>
                  <div style={{ display: "flex", gap: 16 }}>
                    <div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: "#1f2937" }}>{MOCK.bodyComp.body_fat}%</div>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>体脂率</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: "#1f2937" }}>{MOCK.bodyComp.muscle_mass}</div>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>肌肉kg</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 22, fontWeight: 700, color: "#1f2937" }}>{MOCK.bodyComp.visceral_fat}</div>
                      <div style={{ fontSize: 11, color: "#9ca3af" }}>内脏脂肪</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── 8. 7-Day Trends (4 metrics) ── */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {[
                  { icon: "❤️", label: "心率", data: last7.map(r => r.hr), prevData: prev7.map(r => r.hr), unit: "bpm", color: "#ef4444", goodDown: true },
                  { icon: "💓", label: "HRV", data: last7.map(r => r.hrv), prevData: prev7.map(r => r.hrv), unit: "ms", color: "#6366f1", goodDown: false },
                  { icon: "😤", label: "压力", data: last7.map(r => r.stress), prevData: prev7.map(r => r.stress), unit: "", color: "#f59e0b", goodDown: true },
                  { icon: "🚶", label: "步数", data: last7.map(r => r.steps), prevData: prev7.map(r => r.steps), unit: "步", color: "#22c55e", goodDown: false },
                ].map(t => {
                  const curAvg = Math.round(avg(t.data));
                  const prevAvg = Math.round(avg(t.prevData));
                  const change = Number(pctChange(curAvg, prevAvg));
                  const isGood = t.goodDown ? change <= 0 : change >= 0;
                  return (
                    <div key={t.label} style={{ ...card, padding: 16 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 14, fontWeight: 500, color: "#4b5563" }}>{t.icon} {t.label} 7日</span>
                        <span style={{ fontSize: 12, fontWeight: 500, padding: "2px 8px", borderRadius: 12, background: isGood ? "#f0fdf4" : "#fef2f2", color: isGood ? "#16a34a" : "#ef4444" }}>
                          {change >= 0 ? "+" : ""}{change}%
                        </span>
                      </div>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 8 }}>
                        <span style={{ fontSize: 20, fontWeight: 700, color: "#1f2937" }}>{curAvg || "--"}</span>
                        <span style={{ fontSize: 12, color: "#9ca3af" }}>{t.unit}</span>
                      </div>
                      <Sparkline data={t.data} color={t.color} />
                    </div>
                  );
                })}
              </div>

              {/* ── 9. Recent Workouts ── */}
              <div style={{ ...card }}>
                {sectionTitle("🏋️", "最近运动", <button style={{ fontSize: 12, color: "#059669", background: "none", border: "none", cursor: "pointer" }}>查看全部</button>)}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {MOCK.workouts.map((w, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 0", borderBottom: i < MOCK.workouts.length - 1 ? "1px solid #f9fafb" : "none" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <div style={{ width: 36, height: 36, borderRadius: 10, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>
                          {w.type === "running" ? "🏃" : w.type === "cycling" ? "🚴" : "💪"}
                        </div>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 500, color: "#374151" }}>{w.name}</div>
                          <div style={{ fontSize: 11, color: "#9ca3af" }}>
                            {w.distance > 0 ? `${w.distance}km · ` : ""}{w.duration}分钟{w.hr ? ` · ${w.hr}bpm` : ""}{w.pace ? ` · ${w.pace}/km` : ""}
                          </div>
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 12, fontWeight: 500, color: "#4b5563" }}>{w.calories}kcal</div>
                        <div style={{ fontSize: 10, color: "#d1d5db" }}>{w.date}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* ── 10. Active Goals ── */}
              <div style={{ ...card }}>
                {sectionTitle("🎯", "进行中的目标", <button style={{ fontSize: 12, color: "#059669", background: "none", border: "none", cursor: "pointer" }}>管理目标</button>)}
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {MOCK.goals.map((g, i) => {
                    const pct = g.target > 0 ? Math.min(100, Math.round((g.current / g.target) * 100)) : 0;
                    const barColor = pct >= 100 ? "#22c55e" : pct >= 50 ? "#3b82f6" : "#f59e0b";
                    return (
                      <div key={i}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <span style={{ fontSize: 14, color: "#374151" }}>{g.title}</span>
                          <span style={{ fontSize: 12, fontWeight: 500, color: "#6b7280" }}>{pct}%</span>
                        </div>
                        <div style={{ height: 6, background: "#f3f4f6", borderRadius: 6, overflow: "hidden" }}>
                          <div style={{ height: "100%", borderRadius: 6, background: barColor, width: `${pct}%`, transition: "width 0.8s" }} />
                        </div>
                        <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 3 }}>
                          {g.current} / {g.target} {g.unit}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* ── 11. Mood & Energy ── */}
              <div style={{ ...card }}>
                {sectionTitle("😊", "今日情绪")}
                <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 40 }}>{MOCK.mood.score >= 8 ? "😄" : MOCK.mood.score >= 6 ? "😊" : MOCK.mood.score >= 4 ? "😐" : "😔"}</div>
                    <div style={{ fontSize: 12, color: "#6b7280", marginTop: 4 }}>{MOCK.mood.score}/10</div>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: 20 }}>
                      <div>
                        <div style={{ fontSize: 11, color: "#9ca3af" }}>精力</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#374151" }}>{MOCK.mood.energy}/10</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: "#9ca3af" }}>压力</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#374151" }}>{MOCK.mood.stress}/10</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: "#9ca3af" }}>焦虑</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#374151" }}>{MOCK.mood.anxiety}/10</div>
                      </div>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
                      {MOCK.mood.tags.map((tag, i) => (
                        <span key={i} style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12, background: "#eff6ff", color: "#2563eb" }}>{tag}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* ── 12. Supplements ── */}
              <div style={{ ...card }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 15 }}>💊</span>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#1f2937" }}>今日补剂</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ height: 6, width: 64, background: "#f3f4f6", borderRadius: 6, overflow: "hidden" }}>
                      <div style={{ height: "100%", background: "#22c55e", borderRadius: 6, width: suppTotal > 0 ? `${(suppChecked / suppTotal) * 100}%` : "0%" }} />
                    </div>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{suppChecked}/{suppTotal}</span>
                  </div>
                </div>
                {(() => {
                  let lastTiming = "";
                  return suppVisible.map((s, i) => {
                    const showHeader = s._timing !== lastTiming;
                    lastTiming = s._timing;
                    return (
                      <div key={i}>
                        {showHeader && <p style={{ fontSize: 11, fontWeight: 500, color: "#9ca3af", margin: "10px 0 4px", textTransform: "uppercase", letterSpacing: 1.5 }}>{timingLabels[s._timing]}</p>}
                        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0" }}>
                          <div style={{ width: 18, height: 18, borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, background: s.taken ? "#22c55e" : "transparent", border: s.taken ? "none" : "1.5px solid #d1d5db" }}>
                            {s.taken && <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3"><path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                          </div>
                          <span style={{ flex: 1, fontSize: 14, color: s.taken ? "#9ca3af" : "#374151", textDecoration: s.taken ? "line-through" : "none" }}>{s.name}</span>
                          {s.dosage && <span style={{ fontSize: 11, color: "#9ca3af" }}>{s.dosage}</span>}
                        </div>
                      </div>
                    );
                  });
                })()}
                {suppFlat.length > 6 && (
                  <button onClick={() => setSuppExpanded(!suppExpanded)}
                    style={{ width: "100%", marginTop: 8, padding: "8px 0", fontSize: 13, color: "#059669", background: "none", border: "none", cursor: "pointer" }}>
                    {suppExpanded ? "收起" : `展开全部 (${suppFlat.length})`}
                  </button>
                )}
              </div>

              {/* ── 13. Quick Actions Grid ── */}
              <div style={{ ...card }}>
                {[
                  { group: "快速记录", items: [
                    { icon: "💧", label: "喝水" }, { icon: "🍽️", label: "饮食" }, { icon: "💊", label: "补剂" },
                    { icon: "😊", label: "情绪" }, { icon: "✅", label: "打卡" }, { icon: "👃", label: "鼻炎" },
                  ]},
                  { group: "健康追踪", items: [
                    { icon: "🏋️", label: "运动" }, { icon: "🌙", label: "睡眠" }, { icon: "⚖️", label: "体重" },
                    { icon: "❤️", label: "心率" }, { icon: "🩺", label: "血压" }, { icon: "⌚", label: "Garmin" },
                  ]},
                  { group: "AI 分析", items: [
                    { icon: "📊", label: "今日概览" }, { icon: "✨", label: "AI洞察" }, { icon: "📅", label: "智能计划" },
                    { icon: "📈", label: "趋势分析" }, { icon: "📋", label: "健康报告" }, { icon: "🧬", label: "基因报告" },
                  ]},
                  { group: "管理", items: [
                    { icon: "🎯", label: "目标" }, { icon: "👨‍👩‍👦", label: "家庭" }, { icon: "🏥", label: "体检" },
                    { icon: "💊", label: "用药" }, { icon: "📊", label: "数据导出" }, { icon: "⚙️", label: "设置" },
                  ]},
                ].map(section => (
                  <div key={section.group} style={{ marginBottom: 16 }}>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 2, color: "#9ca3af", fontWeight: 500, marginBottom: 8 }}>{section.group}</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 4 }}>
                      {section.items.map(item => (
                        <button key={item.label} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, padding: "10px 4px", borderRadius: 12, border: "none", background: "transparent", cursor: "pointer", transition: "background 0.2s" }}
                          onMouseEnter={e => e.currentTarget.style.background = "#f9fafb"}
                          onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                          <span style={{ fontSize: 20 }}>{item.icon}</span>
                          <span style={{ fontSize: 10, color: "#4b5563" }}>{item.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {/* ── 14. Quick Ask Prompts ── */}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {[
                  { label: "今日概览", text: "查一下我今天的健康数据概览" },
                  { label: "睡眠分析", text: "帮我分析一下最近的睡眠质量" },
                  { label: "运动建议", text: "根据我的身体数据，今天适合做什么运动？" },
                  { label: "记录饮食", text: "帮我记录一下刚才吃的饭" },
                  { label: "AI 洞察", text: "查看今日 AI 洞察和健康分析详情" },
                  { label: "趋势报告", text: "分析我最近两周的健康趋势" },
                ].map(q => (
                  <button key={q.label} onClick={() => handleSend(q.text)}
                    style={{ padding: "10px 16px", borderRadius: 14, border: "1px solid #e5e7eb", background: "#fff", fontSize: 14, color: "#4b5563", cursor: "pointer", transition: "all 0.2s" }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "#86efac"; e.currentTarget.style.color = "#059669"; e.currentTarget.style.background = "#f0fdf4"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#e5e7eb"; e.currentTarget.style.color = "#4b5563"; e.currentTarget.style.background = "#fff"; }}>
                    {q.label}
                  </button>
                ))}
              </div>

            </div>
          ) : (
            /* Chat messages view */
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {chatMessages.map((msg, i) => (
                <div key={i} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", gap: 12 }}>
                  {msg.role === "assistant" && (
                    <div style={{ width: 36, height: 36, borderRadius: 14, background: "#f0fdf4", border: "1px solid #bbf7d0", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 4 }}>
                      <span style={{ fontSize: 14 }}>🤖</span>
                    </div>
                  )}
                  <div style={{
                    maxWidth: "75%", borderRadius: 20, padding: "12px 18px", fontSize: 14, lineHeight: 1.8,
                    ...(msg.role === "user"
                      ? { background: "linear-gradient(135deg, #22c55e, #14b8a6)", color: "#fff" }
                      : { background: "#f8fafc", border: "1px solid #e5e7eb", color: "#1f2937" })
                  }}>
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Input Bar */}
      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, padding: "12px 16px 20px", background: "linear-gradient(transparent, #f8fafb 20%)" }}>
        <div style={{ maxWidth: 860, margin: "0 auto", borderRadius: 18, background: "#fff", border: "1px solid #e5e7eb", boxShadow: "0 -2px 16px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 12, padding: "10px 16px" }}>
          <button style={{ width: 36, height: 36, borderRadius: 10, border: "none", background: "transparent", color: "#9ca3af", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>📎</button>
          <button style={{ width: 36, height: 36, borderRadius: 10, border: "none", background: "transparent", color: "#9ca3af", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>🎤</button>
          <input
            type="text"
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); handleSend(inputValue); } }}
            placeholder="用一句完整目标开始，例如：分析今天状态，或帮我安排训练恢复"
            style={{ flex: 1, border: "none", outline: "none", fontSize: 14, color: "#374151", background: "transparent" }}
          />
          <button
            onClick={() => handleSend(inputValue)}
            disabled={!inputValue.trim()}
            style={{
              width: 32, height: 32, borderRadius: 10, border: "none", cursor: inputValue.trim() ? "pointer" : "not-allowed",
              background: inputValue.trim() ? "#22c55e" : "#f3f4f6",
              color: inputValue.trim() ? "#fff" : "#9ca3af",
              display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s",
            }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
