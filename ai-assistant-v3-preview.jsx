import { useState, useEffect, useMemo, useCallback } from "react";

// ============================================================================
// Mock Data — 基于截图中的真实数据
// ============================================================================
const MOCK = {
  user: { name: "baokun" },
  healthScore: {
    total_score: 59,
    dimensions: { exercise: 25, sleep: 82, diet: 42, vitals: 75, weight: 68, hydration: 40 },
    suggestions: ["增加户外运动时间", "饮水量需要提升到1500ml以上", "午餐蛋白质摄入不足"],
  },
  dailyInsight: "昨夜睡眠89分，HRV 68ms，步数5,038，饮水量800ml/2000ml。深睡比例偏低（1.1h），建议今天避免高强度训练，以恢复为主。",
  garmin: {
    resting_heart_rate: 49, avg_heart_rate: 62,
    body_battery_high: 100, body_battery_low: 47, body_battery_current: 100,
    sleep_score: 89, total_sleep_duration: 467,
    deep_sleep_duration: 66, rem_sleep_duration: 86, light_sleep_duration: 317,
    stress_level: 19, hrv: 68, hrv_7day_avg: 62,
    steps: 5038, active_calories: 180, calories_burned: 1820, spo2: 92,
  },
  weather: { city: "杭州", temperature: 28, weather_description: "晴", temp_min: 17, temp_max: 28, humidity: 58 },
  air: { aqi: 58, pm25: 17.5 },
  water: { total_ml: 800, goal_ml: 2000, count: 3 },
  diet: { total_calories: 320, total_protein: 18, total_carbs: 40, total_fat: 6, meals_count: 1 },
  rhinitis: { sneeze_count: 6, nasal_wash_count: 3 },
  weight: { current_weight: 73.6, weight_change: -0.2, bmi: 23.1 },
  bloodPressure: { systolic: 119, diastolic: 75, pulse: 60, date: "04-05", count: 13, label: "正常" },
  bodyComp: { body_fat: 18.2, muscle_mass: 32.4, visceral_fat: 7 },
  supplements: [
    { name: "肌酸", dosage: "2粒", timing: "morning", taken: true },
    { name: "NAC", dosage: "2粒", timing: "morning", taken: true },
    { name: "甘氨酸锌", dosage: "30mg", timing: "morning", taken: true },
    { name: "复合维生素B", dosage: "", timing: "morning", taken: true },
    { name: "Thorne Basic B Complex", dosage: "1 Capsule", timing: "morning", taken: true },
    { name: "泡腾片", dosage: "1粒", timing: "morning", taken: false },
    { name: "维生素D3", dosage: "5000IU", timing: "noon", taken: false },
    { name: "鱼肝油", dosage: "5000IU", timing: "noon", taken: false },
    { name: "辅酶Q10", dosage: "100mg", timing: "noon", taken: false },
    { name: "叶黄素", dosage: "20mg", timing: "noon", taken: false },
    { name: "褪黑素", dosage: "3mg", timing: "bedtime", taken: false },
    { name: "甘氨酸镁", dosage: "400mg", timing: "bedtime", taken: false },
    { name: "益生菌", dosage: "1包", timing: "evening", taken: false },
  ],
  garminHistory: [
    { date: "03-30", hr: 52, hrv: 58, stress: 22, steps: 8200, sleep: 82 },
    { date: "03-31", hr: 48, hrv: 65, stress: 18, steps: 6500, sleep: 85 },
    { date: "04-01", hr: 51, hrv: 62, stress: 25, steps: 9100, sleep: 79 },
    { date: "04-02", hr: 49, hrv: 55, stress: 20, steps: 7300, sleep: 88 },
    { date: "04-03", hr: 47, hrv: 70, stress: 15, steps: 10200, sleep: 91 },
    { date: "04-04", hr: 50, hrv: 64, stress: 19, steps: 5800, sleep: 86 },
    { date: "04-05", hr: 49, hrv: 68, stress: 16, steps: 5038, sleep: 89 },
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
    { name: "跑步", sub: "杭州市·基础训练", type: "running", distance: 3.06, duration: 21, calories: 230, hr: 142, date: "2025-04-05", pace: "6:52" },
    { name: "力量训练", sub: "上肢推拉", type: "strength", distance: 0, duration: 45, calories: 280, hr: 128, date: "2025-04-03" },
    { name: "骑行", sub: "通勤", type: "cycling", distance: 12.5, duration: 38, calories: 310, hr: 125, date: "2025-04-01" },
  ],
  goals: [
    { title: "每周跑步3次", current: 2, target: 3, unit: "次" },
    { title: "体重降至72kg", current: 73.6, target: 72, unit: "kg" },
    { title: "每日饮水2L", current: 800, target: 2000, unit: "ml" },
  ],
  mood: { score: 7, energy: 6, stress: 3, anxiety: 2, tags: ["平静", "专注"], time: "09:30" },
  quickActions: [
    { icon: "💧", label: "喝水350ml", type: "ai" },
    { icon: "👃", label: "洗鼻+1", type: "ai" },
    { icon: "🤧", label: "喷嚏+1", type: "ai" },
    { icon: "☕", label: "咖啡", type: "ai" },
    { icon: "🍵", label: "喝茶", type: "ai" },
    { icon: "💉", label: "注射替尔泊肽", type: "ai" },
  ],
};

// ============================================================================
// SVG 图表组件
// ============================================================================

function AnimatedRing({ score, size = 88, strokeWidth = 7 }) {
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const [offset, setOffset] = useState(c);
  useEffect(() => { const t = setTimeout(() => setOffset(c - (score / 100) * c), 120); return () => clearTimeout(t); }, [score, c]);
  const color = score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={strokeWidth} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)" }} />
    </svg>
  );
}

function ProgressRing({ pct, color, size = 56, sw = 4.5 }) {
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const [off, setOff] = useState(c);
  useEffect(() => { const t = setTimeout(() => setOff(c - (pct / 100) * c), 120); return () => clearTimeout(t); }, [pct, c]);
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={sw} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 1s ease" }} />
    </svg>
  );
}

function Sparkline({ data, color = "#22c55e", w = 120, h = 32 }) {
  if (!data.length) return null;
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`).join(" ");
  const uid = "sp" + color.replace("#", "") + Math.random().toString(36).slice(2, 6);
  return (
    <svg width={w} height={h} style={{ overflow: "visible", display: "block" }}>
      <defs><linearGradient id={uid} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity="0.15" /><stop offset="100%" stopColor={color} stopOpacity="0" /></linearGradient></defs>
      <polygon fill={`url(#${uid})`} points={`0,${h} ${pts} ${w},${h}`} />
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}

function SleepBar({ deep, rem, light }) {
  const t = deep + rem + light;
  if (t <= 0) return null;
  return (
    <div style={{ display: "flex", height: 14, borderRadius: 7, overflow: "hidden", background: "#f3f4f6", gap: 1 }}>
      <div style={{ width: `${(deep / t) * 100}%`, background: "#312e81", borderRadius: "7px 0 0 7px", transition: "width 1s" }} />
      <div style={{ width: `${(rem / t) * 100}%`, background: "#818cf8", transition: "width 1s" }} />
      <div style={{ width: `${(light / t) * 100}%`, background: "#c7d2fe", borderRadius: "0 7px 7px 0", transition: "width 1s" }} />
    </div>
  );
}

// ============================================================================
// 主组件
// ============================================================================
export default function AIAssistantV3() {
  const [suppExpanded, setSuppExpanded] = useState(false);
  const [chatMode, setChatMode] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [activeTab, setActiveTab] = useState("dashboard"); // dashboard | chat

  const g = MOCK.garmin;
  const hs = MOCK.healthScore;
  const hour = new Date().getHours();
  const greeting = hour < 6 ? "夜深了" : hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
  const scoreColor = hs.total_score >= 80 ? "#22c55e" : hs.total_score >= 60 ? "#f59e0b" : "#ef4444";

  // 睡眠
  const sleepH = Math.floor(g.total_sleep_duration / 60);
  const sleepM = Math.round(g.total_sleep_duration % 60);
  const deepH = (g.deep_sleep_duration / 60).toFixed(1);
  const remH = (g.rem_sleep_duration / 60).toFixed(1);
  const lightH = (g.light_sleep_duration / 60).toFixed(1);

  // 趋势
  const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const pctChg = (cur, prev) => prev > 0 ? ((cur - prev) / prev * 100).toFixed(1) : "0";

  // 进度
  const stepsPct = Math.min(100, Math.round((g.steps / 8000) * 100));
  const waterPct = Math.min(100, Math.round((MOCK.water.total_ml / MOCK.water.goal_ml) * 100));
  const suppChecked = MOCK.supplements.filter(s => s.taken).length;
  const suppTotal = MOCK.supplements.length;
  const suppPct = suppTotal > 0 ? Math.round((suppChecked / suppTotal) * 100) : 0;

  // 补剂分组
  const timingLabels = { morning: "早晨", noon: "中午", evening: "晚上", bedtime: "睡前" };
  const suppFlat = ["morning", "noon", "evening", "bedtime"].flatMap(t =>
    MOCK.supplements.filter(s => s.timing === t).map(s => ({ ...s, _timing: t }))
  );
  const suppVisible = suppExpanded ? suppFlat : suppFlat.slice(0, 6);

  // 智能警报
  const alerts = useMemo(() => {
    const list = [];
    if (hour >= 7 && MOCK.water.total_ml < (hour >= 14 ? 1000 : 500)) {
      list.push({ icon: "💧", text: `饮水 ${MOCK.water.total_ml}ml，目标还差 ${MOCK.water.goal_ml - MOCK.water.total_ml}ml`, bg: "linear-gradient(135deg, #fef2f2, #fff1f2)", border: "#fecaca", action: "记录喝水350ml" });
    }
    const remaining = suppTotal - suppChecked;
    if (remaining > 0 && hour >= 7) {
      list.push({ icon: "💊", text: `${remaining}项补剂待服用`, bg: "linear-gradient(135deg, #f5f3ff, #faf5ff)", border: "#e9d5ff", action: "去打卡", link: true });
    }
    if (hour >= 14 && g.steps < 5000) {
      list.push({ icon: "🚶", text: `步数${g.steps.toLocaleString()}，建议起来走走`, bg: "linear-gradient(135deg, #fffbeb, #fef3c7)", border: "#fde68a", action: "运动建议" });
    }
    return list;
  }, []);

  const handleSend = (text) => {
    if (!text?.trim()) return;
    setChatMessages(prev => [...prev, { role: "user", content: text }, { role: "assistant", content: "正在分析中..." }]);
    setInputValue("");
    setChatMode(true);
  };

  const dimNames = { exercise: "运动", sleep: "睡眠", diet: "饮食", vitals: "体征", weight: "体重", hydration: "饮水" };
  const dimIcons = { exercise: "🏃", sleep: "😴", diet: "🍽️", vitals: "❤️", weight: "⚖️", hydration: "💧" };

  // ==================== RENDER ====================
  return (
    <div style={{ fontFamily: '-apple-system, "PingFang SC", "Hiragino Sans GB", sans-serif', background: "#f7f8fa", minHeight: "100vh" }}>
      {/* Header */}
      <header style={{ position: "sticky", top: 0, zIndex: 50, background: "rgba(255,255,255,0.92)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", borderBottom: "1px solid rgba(0,0,0,0.04)" }}>
        <div style={{ maxWidth: 860, margin: "0 auto", padding: "0 20px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 9, background: "linear-gradient(135deg, #10b981, #059669)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 13, fontWeight: 700 }}>H</div>
            <span style={{ fontWeight: 600, fontSize: 15, color: "#111827" }}>智能助理</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button style={{ color: "#9ca3af", background: "none", border: "none", cursor: "pointer" }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <button style={{ color: "#9ca3af", background: "none", border: "none", cursor: "pointer", fontSize: 20, lineHeight: 1 }}>+</button>
            <div style={{ width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg, #a78bfa, #7c3aed)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 600 }}>b</div>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 860, margin: "0 auto", padding: "16px 16px 140px" }}>
        {!chatMode ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

            {/* ━━━ 1. STATUS HERO ━━━ */}
            <div style={{ borderRadius: 20, padding: "20px 22px", background: "linear-gradient(135deg, #1a1025 0%, #1e1b4b 50%, #312e81 100%)", position: "relative", overflow: "hidden" }}>
              {/* Glow */}
              <div style={{ position: "absolute", top: -60, right: -30, width: 200, height: 200, borderRadius: "50%", background: `radial-gradient(circle, ${scoreColor}25, transparent 70%)` }} />
              <div style={{ position: "absolute", bottom: -40, left: "30%", width: 160, height: 160, borderRadius: "50%", background: "radial-gradient(circle, rgba(99,102,241,0.15), transparent 70%)" }} />

              <div style={{ position: "relative", zIndex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <h1 style={{ fontSize: 17, fontWeight: 600, color: "#fff", margin: 0 }}>{greeting}</h1>
                  <button style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    刷新
                  </button>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                  <div style={{ position: "relative", flexShrink: 0 }}>
                    <AnimatedRing score={hs.total_score} size={82} strokeWidth={6} />
                    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                      <span style={{ fontSize: 24, fontWeight: 700, color: "#fff", lineHeight: 1 }}>{hs.total_score}</span>
                      <span style={{ fontSize: 9, color: "rgba(255,255,255,0.4)", marginTop: 2 }}>健康分</span>
                    </div>
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: scoreColor }}>
                        {hs.total_score >= 80 ? "状态优秀" : hs.total_score >= 60 ? "状态一般" : "需要关注"}
                      </span>
                    </div>
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", lineHeight: 1.7, margin: 0, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {MOCK.dailyInsight}
                    </p>

                    {/* Dimension bars */}
                    <div style={{ display: "flex", gap: 3, marginTop: 10 }}>
                      {Object.entries(hs.dimensions).map(([k, v]) => {
                        const bc = v >= 70 ? "#22c55e" : v >= 40 ? "#f59e0b" : "#ef4444";
                        return (
                          <div key={k} style={{ flex: 1 }}>
                            <div style={{ height: 3, borderRadius: 3, background: "rgba(255,255,255,0.06)", overflow: "hidden" }}>
                              <div style={{ height: "100%", borderRadius: 3, background: bc, width: `${v}%`, transition: "width 0.8s" }} />
                            </div>
                            <div style={{ fontSize: 8, color: "rgba(255,255,255,0.25)", textAlign: "center", marginTop: 3 }}>{dimNames[k]?.charAt(0)}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* ━━━ 2. SMART ALERTS ━━━ */}
            {alerts.map((a, i) => (
              <button key={i} onClick={() => a.link ? null : handleSend(a.action)} style={{
                width: "100%", borderRadius: 14, padding: "11px 14px", display: "flex", alignItems: "center", gap: 10,
                background: a.bg, border: `1px solid ${a.border}`, cursor: "pointer", textAlign: "left",
              }}>
                <span style={{ fontSize: 16 }}>{a.icon}</span>
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: "#374151" }}>{a.text}</span>
                {a.link ? (
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#7c3aed", background: "#ede9fe", padding: "4px 12px", borderRadius: 8 }}>去打卡</span>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2"><path d="M9 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round"/></svg>
                )}
              </button>
            ))}

            {/* ━━━ 3. BODY SNAPSHOT — 2x2 compact grid ━━━ */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
              {[
                { icon: "❤️", val: g.resting_heart_rate, unit: "bpm", label: "心率", ok: v => v >= 45 && v <= 80 },
                { icon: "🔋", val: g.body_battery_current, unit: "", label: "电量", sub: `当前${g.body_battery_low}`, ok: v => v >= 50 },
                { icon: "😴", val: g.sleep_score, unit: "分", label: "睡眠", sub: `${sleepH}h${sleepM}m`, ok: v => v >= 70 },
                { icon: "😌", val: g.stress_level, unit: "", label: "压力", ok: v => v <= 40 },
              ].map(m => {
                const warn = m.val != null && !m.ok(m.val);
                return (
                  <div key={m.label} style={{ background: warn ? "#fffbeb" : "#fff", borderRadius: 16, padding: "14px 10px", textAlign: "center", border: "1px solid #f0f0f0" }}>
                    <span style={{ fontSize: 18 }}>{m.icon}</span>
                    <div style={{ fontSize: 26, fontWeight: 700, color: warn ? "#f59e0b" : "#111827", marginTop: 2, lineHeight: 1.2 }}>
                      {m.val ?? "--"}
                      {m.unit && <span style={{ fontSize: 11, fontWeight: 400, color: "#9ca3af", marginLeft: 2 }}>{m.unit}</span>}
                    </div>
                    <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 3 }}>{m.label}</div>
                    {m.sub && <div style={{ fontSize: 10, color: "#b0b0b0", marginTop: 1 }}>{m.sub}</div>}
                  </div>
                );
              })}
            </div>

            {/* ━━━ 4. CONTEXT ROW — weather / diet / rhinitis / weight ━━━ */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>
              {/* Weather */}
              <div style={{ background: "linear-gradient(160deg, #eef2ff, #e0f2fe)", borderRadius: 16, padding: 14, border: "1px solid #dbeafe60" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>{MOCK.weather.city}</span>
                  <span style={{ fontSize: 11, color: "#64748b" }}>{MOCK.weather.weather_description}</span>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                  <span style={{ fontSize: 28, fontWeight: 700, color: "#0f172a" }}>{MOCK.weather.temperature}°</span>
                  <span style={{ fontSize: 11, color: "#94a3b8" }}>{MOCK.weather.temp_min}°/{MOCK.weather.temp_max}°</span>
                </div>
                <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                  <span style={{ fontSize: 10, fontWeight: 500, padding: "2px 5px", borderRadius: 4, background: MOCK.air.aqi <= 50 ? "#dcfce7" : "#fef9c3", color: MOCK.air.aqi <= 50 ? "#16a34a" : "#ca8a04" }}>AQI {MOCK.air.aqi}</span>
                  <span style={{ fontSize: 10, fontWeight: 500, padding: "2px 5px", borderRadius: 4, background: "#f0fdf4", color: "#16a34a" }}>PM2.5 {MOCK.air.pm25}</span>
                </div>
              </div>
              {/* Diet */}
              <div style={{ background: "linear-gradient(160deg, #fff7ed, #fefce8)", borderRadius: 16, padding: 14, border: "1px solid #fed7aa50" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>饮食</span>
                  <span style={{ fontSize: 11, color: "#94a3b8" }}>{MOCK.diet.meals_count}餐</span>
                </div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "#0f172a" }}>{MOCK.diet.total_calories}<span style={{ fontSize: 11, fontWeight: 400, color: "#94a3b8", marginLeft: 2 }}>kcal</span></div>
                <div style={{ display: "flex", gap: 6, marginTop: 6, fontSize: 10, color: "#78716c" }}>
                  <span><b style={{ color: "#ef4444" }}>{MOCK.diet.total_protein}g</b> 蛋白</span>
                  <span><b style={{ color: "#f59e0b" }}>{MOCK.diet.total_carbs}g</b> 碳水</span>
                  <span><b style={{ color: "#22c55e" }}>{MOCK.diet.total_fat}g</b> 脂肪</span>
                </div>
              </div>
              {/* Rhinitis */}
              <div style={{ background: "linear-gradient(160deg, #faf5ff, #fdf4ff)", borderRadius: 16, padding: 14, border: "1px solid #e9d5ff50" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>👃 鼻炎</div>
                <div style={{ display: "flex", gap: 14 }}>
                  <div><div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a" }}>{MOCK.rhinitis.sneeze_count}</div><div style={{ fontSize: 10, color: "#94a3b8" }}>喷嚏</div></div>
                  <div><div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a" }}>{MOCK.rhinitis.nasal_wash_count}<span style={{ fontSize: 12, color: "#94a3b8" }}>/2</span></div><div style={{ fontSize: 10, color: "#94a3b8" }}>洗鼻</div></div>
                </div>
              </div>
              {/* Weight */}
              <div style={{ background: "linear-gradient(160deg, #f0fdf4, #ecfdf5)", borderRadius: 16, padding: 14, border: "1px solid #bbf7d050" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 6 }}>⚖️ 体重</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "#0f172a" }}>{MOCK.weight.current_weight}<span style={{ fontSize: 11, fontWeight: 400, color: "#94a3b8", marginLeft: 2 }}>kg</span></div>
                <div style={{ fontSize: 11, fontWeight: 500, color: MOCK.weight.weight_change <= 0 ? "#16a34a" : "#ef4444", marginTop: 3 }}>
                  30天 {MOCK.weight.weight_change > 0 ? "+" : ""}{MOCK.weight.weight_change}kg
                </div>
              </div>
            </div>

            {/* ━━━ 5. PROGRESS RINGS ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "16px 20px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                {[
                  { pct: stepsPct, color: "#6366f1", label: "步数", display: g.steps.toLocaleString(), sub: "/8,000" },
                  { pct: waterPct, color: "#3b82f6", label: "饮水", display: String(MOCK.water.total_ml), sub: `/${MOCK.water.goal_ml}ml` },
                  { pct: suppPct, color: "#8b5cf6", label: "补剂", display: `${suppChecked}/${suppTotal}`, sub: "" },
                ].map(r => (
                  <div key={r.label} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <div style={{ position: "relative", width: 56, height: 56 }}>
                      <ProgressRing pct={r.pct} color={r.color} />
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#374151" }}>{r.pct}%</div>
                    </div>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "#1f2937", marginTop: 6 }}>{r.display}</span>
                    {r.sub && <span style={{ fontSize: 11, color: "#9ca3af" }}>{r.sub}</span>}
                    <span style={{ fontSize: 11, color: "#9ca3af" }}>{r.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* ━━━ 6. SLEEP DETAIL ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "16px 18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>🌙 昨夜睡眠详情</span>
                <span style={{ fontSize: 12, color: "#9ca3af" }}>{sleepH}h{sleepM}m</span>
              </div>
              <SleepBar deep={g.deep_sleep_duration} rem={g.rem_sleep_duration} light={g.light_sleep_duration} />
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8, fontSize: 11, color: "#6b7280" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "#312e81", display: "inline-block" }}/> 深睡 {deepH}h</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "#818cf8", display: "inline-block" }}/> REM {remH}h</span>
                <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: 2, background: "#c7d2fe", display: "inline-block" }}/> 浅睡 {lightH}h</span>
              </div>
              <div style={{ display: "flex", gap: 20, marginTop: 12, paddingTop: 10, borderTop: "1px solid #f5f5f5" }}>
                <div><span style={{ fontSize: 22, fontWeight: 700, color: "#111" }}>{g.sleep_score}</span><span style={{ fontSize: 11, color: "#9ca3af", marginLeft: 4 }}>睡眠分</span></div>
                <div><span style={{ fontSize: 18, fontWeight: 600, color: "#374151" }}>{g.hrv}</span><span style={{ fontSize: 11, color: "#9ca3af", marginLeft: 4 }}>HRV ms</span></div>
                <div><span style={{ fontSize: 18, fontWeight: 600, color: "#374151" }}>{g.spo2}</span><span style={{ fontSize: 11, color: "#9ca3af", marginLeft: 4 }}>SpO2 %</span></div>
              </div>
            </div>

            {/* ━━━ 7. BLOOD PRESSURE ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "16px 18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>🩺 血压（近30天均值）</span>
                <span style={{ fontSize: 11, color: "#9ca3af" }}>{MOCK.bloodPressure.count}次记录</span>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                <span style={{ fontSize: 30, fontWeight: 700, color: "#111827" }}>{MOCK.bloodPressure.systolic}/{MOCK.bloodPressure.diastolic}</span>
                <span style={{ fontSize: 13, color: "#6b7280" }}>mmHg</span>
                <span style={{ fontSize: 13, color: "#6b7280" }}>脉搏 {MOCK.bloodPressure.pulse} bpm</span>
                <span style={{ fontSize: 12, fontWeight: 500, padding: "2px 8px", borderRadius: 6, background: "#dcfce7", color: "#16a34a" }}>{MOCK.bloodPressure.label}</span>
              </div>
            </div>

            {/* ━━━ 8. RECENT WORKOUTS ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "16px 18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>🏃 最近运动</span>
                <span style={{ fontSize: 12, color: "#059669", cursor: "pointer" }}>查看全部</span>
              </div>
              {MOCK.workouts.map((w, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0", borderTop: i > 0 ? "1px solid #f9fafb" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, flexShrink: 0 }}>
                      {w.type === "running" ? "🏃" : w.type === "cycling" ? "🚴" : "💪"}
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>
                        {w.name}{w.sub ? <span style={{ fontSize: 11, color: "#9ca3af", marginLeft: 6 }}>{w.sub}</span> : null}
                      </div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right", fontSize: 12, color: "#6b7280" }}>
                    {w.distance > 0 ? `${w.distance}km ` : ""}{w.duration}min <span style={{ color: "#f59e0b", fontWeight: 500 }}>{w.calories}kcal</span>
                    <div style={{ fontSize: 10, color: "#d1d5db" }}>{w.date}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* ━━━ 9. 7-DAY TRENDS (4 metrics) ━━━ */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {[
                { icon: "❤️", label: "心率", data: MOCK.garminHistory.map(r => r.hr), prev: MOCK.prevHistory.map(r => r.hr), unit: "bpm", color: "#ef4444", goodDown: true },
                { icon: "💓", label: "HRV", data: MOCK.garminHistory.map(r => r.hrv), prev: MOCK.prevHistory.map(r => r.hrv), unit: "ms", color: "#6366f1", goodDown: false },
                { icon: "😤", label: "压力", data: MOCK.garminHistory.map(r => r.stress), prev: MOCK.prevHistory.map(r => r.stress), unit: "", color: "#f59e0b", goodDown: true },
                { icon: "🚶", label: "步数", data: MOCK.garminHistory.map(r => r.steps), prev: MOCK.prevHistory.map(r => r.steps), unit: "步", color: "#22c55e", goodDown: false },
              ].map(t => {
                const curAvg = Math.round(avg(t.data));
                const prevAvg = Math.round(avg(t.prev));
                const chg = Number(pctChg(curAvg, prevAvg));
                const good = t.goodDown ? chg <= 0 : chg >= 0;
                return (
                  <div key={t.label} style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: "#4b5563" }}>{t.icon} {t.label} 7日</span>
                      <span style={{ fontSize: 11, fontWeight: 500, padding: "2px 7px", borderRadius: 10, background: good ? "#f0fdf4" : "#fef2f2", color: good ? "#16a34a" : "#ef4444" }}>{chg >= 0 ? "+" : ""}{chg}%</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 3, marginBottom: 6 }}>
                      <span style={{ fontSize: 20, fontWeight: 700, color: "#111827" }}>{curAvg}</span>
                      <span style={{ fontSize: 11, color: "#9ca3af" }}>{t.unit}</span>
                    </div>
                    <Sparkline data={t.data} color={t.color} />
                  </div>
                );
              })}
            </div>

            {/* ━━━ 10. SUPPLEMENTS ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "14px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 14 }}>💊</span>
                  <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>今日补剂</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ height: 5, width: 50, background: "#f3f4f6", borderRadius: 5, overflow: "hidden" }}>
                    <div style={{ height: "100%", background: "#22c55e", borderRadius: 5, width: `${(suppChecked / suppTotal) * 100}%`, transition: "width 0.5s" }} />
                  </div>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{suppChecked}/{suppTotal}</span>
                </div>
              </div>
              {(() => {
                let last = "";
                return suppVisible.map((s, i) => {
                  const hdr = s._timing !== last;
                  last = s._timing;
                  return (
                    <div key={i}>
                      {hdr && <div style={{ fontSize: 10, fontWeight: 500, color: "#9ca3af", margin: "8px 0 4px", textTransform: "uppercase", letterSpacing: 1.5 }}>{timingLabels[s._timing]}</div>}
                      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
                        <div style={{ width: 16, height: 16, borderRadius: 4, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: s.taken ? "#22c55e" : "transparent", border: s.taken ? "none" : "1.5px solid #d1d5db" }}>
                          {s.taken && <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3"><path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                        </div>
                        <span style={{ flex: 1, fontSize: 13, color: s.taken ? "#9ca3af" : "#374151", textDecoration: s.taken ? "line-through" : "none" }}>{s.name}</span>
                        {s.dosage && <span style={{ fontSize: 11, color: "#b0b0b0" }}>{s.dosage}</span>}
                      </div>
                    </div>
                  );
                });
              })()}
              {suppFlat.length > 6 && (
                <button onClick={() => setSuppExpanded(!suppExpanded)} style={{ width: "100%", marginTop: 6, padding: "6px 0", fontSize: 12, color: "#059669", background: "none", border: "none", cursor: "pointer" }}>
                  {suppExpanded ? "收起" : `展开全部 (${suppFlat.length})`}
                </button>
              )}
            </div>

            {/* ━━━ 11. QUICK RECORD — one-tap actions ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "14px 18px" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 10 }}>快速记录</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {MOCK.quickActions.map((a, i) => (
                  <button key={i} onClick={() => handleSend(a.label)} style={{
                    display: "flex", alignItems: "center", gap: 4, padding: "7px 12px", borderRadius: 20,
                    border: "1px solid #e5e7eb", background: "#fafafa", fontSize: 13, color: "#374151", cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                    onMouseEnter={e => { e.currentTarget.style.borderColor = "#a7f3d0"; e.currentTarget.style.background = "#f0fdf4"; }}
                    onMouseLeave={e => { e.currentTarget.style.borderColor = "#e5e7eb"; e.currentTarget.style.background = "#fafafa"; }}>
                    <span>{a.icon}</span> {a.label}
                  </button>
                ))}
              </div>
            </div>

            {/* ━━━ 12. HEALTH NAVIGATION GRID ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "14px 18px" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 12 }}>健康管理</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
                {[
                  { icon: "💊", label: "补剂" }, { icon: "🍽️", label: "饮食" }, { icon: "💧", label: "饮水" },
                  { icon: "👃", label: "鼻炎" }, { icon: "😊", label: "情绪" }, { icon: "🏋️", label: "运动" },
                  { icon: "📦", label: "产品库" },
                  { icon: "🌙", label: "睡眠" }, { icon: "⚖️", label: "体重" }, { icon: "❤️", label: "心率" },
                  { icon: "🩺", label: "血压" }, { icon: "⌚", label: "Garmin" }, { icon: "🧬", label: "基因" },
                  { icon: "⚙️", label: "设置" },
                ].map(item => (
                  <button key={item.label} style={{
                    display: "flex", flexDirection: "column", alignItems: "center", gap: 3, padding: "8px 2px",
                    borderRadius: 10, border: "none", background: "transparent", cursor: "pointer", fontSize: 10, color: "#4b5563",
                    transition: "background 0.15s",
                  }}
                    onMouseEnter={e => e.currentTarget.style.background = "#f3f4f6"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    <span style={{ fontSize: 22 }}>{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* ━━━ 13. DIMENSION DETAIL — 健康评分分维度 ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "14px 18px" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#111827", marginBottom: 10 }}>📊 健康维度详情</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                {Object.entries(hs.dimensions).map(([k, v]) => {
                  const bc = v >= 70 ? "#22c55e" : v >= 40 ? "#f59e0b" : "#ef4444";
                  return (
                    <div key={k} style={{ padding: "10px", borderRadius: 12, background: "#f9fafb", textAlign: "center" }}>
                      <span style={{ fontSize: 18 }}>{dimIcons[k]}</span>
                      <div style={{ fontSize: 20, fontWeight: 700, color: bc, marginTop: 2 }}>{v}</div>
                      <div style={{ fontSize: 11, color: "#6b7280" }}>{dimNames[k]}</div>
                      <div style={{ height: 3, borderRadius: 3, background: "#e5e7eb", marginTop: 6, overflow: "hidden" }}>
                        <div style={{ height: "100%", borderRadius: 3, background: bc, width: `${v}%`, transition: "width 0.8s" }} />
                      </div>
                    </div>
                  );
                })}
              </div>
              {hs.suggestions?.length > 0 && (
                <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid #f5f5f5" }}>
                  <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>AI 建议</div>
                  {hs.suggestions.map((s, i) => (
                    <div key={i} style={{ fontSize: 12, color: "#4b5563", padding: "3px 0", display: "flex", gap: 6 }}>
                      <span style={{ color: "#d1d5db" }}>•</span> {s}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* ━━━ 14. GOALS ━━━ */}
            <div style={{ background: "#fff", borderRadius: 16, border: "1px solid #f0f0f0", padding: "14px 18px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: "#111827" }}>🎯 目标追踪</span>
                <span style={{ fontSize: 12, color: "#059669", cursor: "pointer" }}>管理</span>
              </div>
              {MOCK.goals.map((goal, i) => {
                const pct = goal.target > 0 ? Math.min(100, Math.round((goal.current / goal.target) * 100)) : 0;
                const bc = pct >= 100 ? "#22c55e" : pct >= 50 ? "#3b82f6" : "#f59e0b";
                return (
                  <div key={i} style={{ marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                      <span style={{ color: "#374151" }}>{goal.title}</span>
                      <span style={{ fontSize: 12, fontWeight: 500, color: "#6b7280" }}>{goal.current}/{goal.target}{goal.unit}</span>
                    </div>
                    <div style={{ height: 5, background: "#f3f4f6", borderRadius: 5, overflow: "hidden" }}>
                      <div style={{ height: "100%", borderRadius: 5, background: bc, width: `${pct}%`, transition: "width 0.8s" }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* ━━━ 15. QUICK ASK ━━━ */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {[
                { label: "睡眠分析", text: "帮我分析最近的睡眠质量" },
                { label: "运动建议", text: "根据我的身体数据，今天适合做什么运动？" },
                { label: "记录饮食", text: "帮我记录一下刚才吃的饭" },
                { label: "AI 洞察", text: "查看今日 AI 洞察和健康分析详情" },
                { label: "趋势报告", text: "分析我最近两周的健康趋势" },
              ].map(q => (
                <button key={q.label} onClick={() => handleSend(q.text)} style={{
                  padding: "8px 14px", borderRadius: 12, border: "1px solid #e5e7eb", background: "#fff",
                  fontSize: 13, color: "#4b5563", cursor: "pointer", transition: "all 0.15s",
                }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#86efac"; e.currentTarget.style.color = "#059669"; e.currentTarget.style.background = "#f0fdf4"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "#e5e7eb"; e.currentTarget.style.color = "#4b5563"; e.currentTarget.style.background = "#fff"; }}>
                  {q.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          /* ━━━ CHAT VIEW ━━━ */
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <button onClick={() => { setChatMode(false); setChatMessages([]); }} style={{ alignSelf: "flex-start", fontSize: 13, color: "#059669", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "6px 14px", cursor: "pointer" }}>
              ← 返回仪表板
            </button>
            {chatMessages.map((msg, i) => (
              <div key={i} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", gap: 10 }}>
                {msg.role === "assistant" && <div style={{ width: 32, height: 32, borderRadius: 12, background: "#f0fdf4", border: "1px solid #d1fae5", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, flexShrink: 0 }}>🤖</div>}
                <div style={{ maxWidth: "75%", borderRadius: 18, padding: "10px 16px", fontSize: 14, lineHeight: 1.8, ...(msg.role === "user" ? { background: "linear-gradient(135deg, #10b981, #059669)", color: "#fff" } : { background: "#fff", border: "1px solid #e5e7eb", color: "#1f2937" }) }}>
                  {msg.content}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* ━━━ INPUT BAR ━━━ */}
      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, padding: "8px 16px max(12px, env(safe-area-inset-bottom))", background: "linear-gradient(transparent, #f7f8fa 30%)" }}>
        <div style={{ maxWidth: 860, margin: "0 auto", borderRadius: 16, background: "#fff", border: "1px solid #e5e7eb", boxShadow: "0 -1px 12px rgba(0,0,0,0.03)", display: "flex", alignItems: "center", gap: 8, padding: "8px 12px" }}>
          <button style={{ width: 34, height: 34, borderRadius: 8, border: "none", background: "transparent", color: "#9ca3af", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
          <button style={{ width: 34, height: 34, borderRadius: 8, border: "none", background: "transparent", color: "#9ca3af", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
          <input type="text" value={inputValue} onChange={e => setInputValue(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); handleSend(inputValue); } }}
            placeholder="用一句完整目标开始，例如：分析今天状态，或帮我安排训练恢复"
            style={{ flex: 1, border: "none", outline: "none", fontSize: 14, color: "#374151", background: "transparent" }} />
          <button onClick={() => handleSend(inputValue)} disabled={!inputValue.trim()} style={{
            width: 32, height: 32, borderRadius: 8, border: "none",
            background: inputValue.trim() ? "#10b981" : "#f3f4f6",
            color: inputValue.trim() ? "#fff" : "#9ca3af",
            cursor: inputValue.trim() ? "pointer" : "not-allowed",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
