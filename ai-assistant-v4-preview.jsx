import { useState, useEffect, useMemo } from "react";

// ============================================================================
// 真实数据模拟 — 基于截图 2025-04-05 晚间
// ============================================================================
const D = {
  user: "baokun",
  date: "4月5日 星期日",
  score: 75,
  dims: { exercise: 80, sleep: 89, diet: 45, vitals: 82, weight: 50, hydration: 100 },
  insight: "睡眠89分，HRV 68ms，9,526步，饮水2100ml。深睡偏低（1.1h），建议明天以恢复性训练为主。",
  suggestions: ["午餐蛋白质不足，晚餐补充至少30g", "深睡偏低，睡前避免蓝光", "体重趋势良好，继续保持"],
  garmin: {
    hr: 49, battery: 100, batteryLow: 47, sleepScore: 89,
    sleepH: 7, sleepM: 47, deep: 84, rem: 86, light: 317,
    stress: 26, hrv: 68, spo2: 93, steps: 9526,
    activeCal: 533, activeMin: 56, floors: 5,
  },
  weather: { city: "杭州", temp: 22, desc: "晴", low: 19, high: 22, aqi: 64, pm25: 21.33 },
  diet: { cal: 338, protein: 40, carbs: 18, fat: 6, meals: 2 },
  rhinitis: { sneeze: 6, wash: 4 },
  weight: { current: 73.6, change: -0.2 },
  water: { ml: 2100, goal: 2000 },
  bp: { sys: 119, dia: 75, pulse: 60, label: "正常", count: 13 },
  medExams: [
    { name: "同型半胱氨酸", val: 7.9, unit: "μmol/L", change: -25.5, trend: [12, 10.5, 9, 8.2, 7.9], good: true },
    { name: "谷丙转氨酶", val: 47, unit: "U/L", change: -13, trend: [62, 55, 52, 49, 47], good: true },
    { name: "白蛋白肌酐比", val: 78, unit: "μ/L", change: 18.1, trend: [55, 60, 65, 72, 78], good: false },
    { name: "总胆固醇", val: 4.84, unit: "mmol/L", change: -4.8, trend: [5.2, 5.1, 5.0, 4.9, 4.84], good: true },
    { name: "空腹血糖", val: 5.66, unit: "mmol/L", change: -2.2, trend: [5.9, 5.8, 5.75, 5.7, 5.66], good: true },
    { name: "尿酸", val: 341, unit: "μmol/L", change: -4.3, trend: [380, 370, 360, 350, 341], good: true },
  ],
  meds: [{ name: "替尔泊肽", dosage: "2.4ml", taken: true, total: 1 }],
  workouts: [
    { name: "跑步", sub: "杭州市 跑步", dist: 2.03, dur: 13, cal: 150, date: "2025-04-05" },
    { name: "跑步", sub: "杭州市·基础训练", dist: 3.06, dur: 21, cal: 230, date: "2025-04-05" },
  ],
  trends: {
    hr: { data: [52, 48, 51, 49, 47, 50, 49], prev: [54, 52, 55, 53, 51, 50, 52], unit: "bpm" },
    hrv: { data: [58, 65, 62, 55, 70, 64, 68], prev: [52, 48, 50, 55, 58, 54, 56], unit: "ms" },
    stress: { data: [22, 18, 25, 20, 15, 19, 26], prev: [28, 30, 26, 24, 22, 25, 23], unit: "" },
    steps: { data: [8200, 6500, 9100, 7300, 10200, 5800, 9526], prev: [7100, 6200, 8400, 7800, 9000, 6900, 7500], unit: "步" },
  },
  supplements: [
    { name: "Life Extension BioActive Complete B-Complex", dosage: "2 Vegetarian Capsules", timing: "morning", taken: true },
    { name: "Life Extension TMG 500mg", dosage: "2 Liquid Vegetarian Capsules", timing: "morning", taken: true },
    { name: "肌酸", dosage: "2粒", timing: "morning", taken: true },
    { name: "NAC", dosage: "2粒", timing: "morning", taken: true },
    { name: "甘氨酸锌", dosage: "30mg", timing: "morning", taken: true },
    { name: "复合维生素B", dosage: "", timing: "morning", taken: true },
    { name: "泡腾片", dosage: "1粒", timing: "morning", taken: true },
    { name: "维生素D3", dosage: "5000IU", timing: "noon", taken: false },
    { name: "鱼肝油", dosage: "5000IU", timing: "noon", taken: false },
    { name: "辅酶Q10", dosage: "100mg", timing: "noon", taken: false },
    { name: "叶黄素", dosage: "20mg", timing: "noon", taken: false },
    { name: "甘氨酸镁", dosage: "400mg", timing: "bedtime", taken: false },
    { name: "甘氨酸", dosage: "3g", timing: "bedtime", taken: false },
    { name: "褪黑素", dosage: "3mg", timing: "bedtime", taken: false },
    { name: "益生菌", dosage: "1包", timing: "evening", taken: false },
    { name: "Thorne Basic B Complex", dosage: "1 Capsule", timing: "morning", taken: false },
  ],
  quickRecord: [
    { icon: "💧", label: "250ml" }, { icon: "💧", label: "500ml" },
    { icon: "👃", label: "洗鼻+1" }, { icon: "🤧", label: "喷嚏+1" },
    { icon: "💉", label: "注射替尔泊肽" },
  ],
  goals: [
    { title: "每周跑步3次", cur: 2, target: 3, unit: "次" },
    { title: "体重降至72kg", cur: 73.6, target: 72, unit: "kg" },
    { title: "同型半胱氨酸<6", cur: 7.9, target: 6, unit: "μmol/L" },
  ],
};

// ============================================================================
// SVG 组件
// ============================================================================
function Ring({ val, max = 100, size = 80, sw = 6, color }) {
  const r = (size - sw) / 2, c = 2 * Math.PI * r;
  const [off, setOff] = useState(c);
  useEffect(() => { const t = setTimeout(() => setOff(c - (Math.min(val, max) / max) * c), 80); return () => clearTimeout(t); }, [val, max, c]);
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={sw} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color || "#22c55e"} strokeWidth={sw}
        strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 1s cubic-bezier(.4,0,.2,1)" }} />
    </svg>
  );
}

function MiniRing({ pct, color, size = 48, sw = 4 }) {
  const r = (size - sw) / 2, c = 2 * Math.PI * r;
  const [off, setOff] = useState(c);
  useEffect(() => { const t = setTimeout(() => setOff(c - (pct / 100) * c), 80); return () => clearTimeout(t); }, [pct, c]);
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#f3f4f6" strokeWidth={sw} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={sw}
        strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
        style={{ transition: "stroke-dashoffset 0.8s ease" }} />
    </svg>
  );
}

function Spark({ data, color = "#22c55e", w = 80, h = 28 }) {
  if (!data?.length) return null;
  const mx = Math.max(...data), mn = Math.min(...data), rg = mx - mn || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / rg) * (h - 4) - 2}`).join(" ");
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <defs><linearGradient id={`sg${color.slice(1)}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity=".12"/><stop offset="100%" stopColor={color} stopOpacity="0"/></linearGradient></defs>
      <polygon fill={`url(#sg${color.slice(1)})`} points={`0,${h} ${pts} ${w},${h}`} />
      <polyline fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}

// ============================================================================
// 通用样式
// ============================================================================
const F = '-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif';
const card = { background: "#fff", borderRadius: 14, border: "1px solid #eee", padding: "14px 16px" };
const dimMap = { exercise: { n: "运动", i: "🏃" }, sleep: { n: "睡眠", i: "😴" }, diet: { n: "饮食", i: "🍽️" }, vitals: { n: "体征", i: "❤️" }, weight: { n: "体重", i: "⚖️" }, hydration: { n: "水分", i: "💧" } };
const avg = arr => arr.reduce((a, b) => a + b, 0) / arr.length;
const pct = (c, p) => p > 0 ? ((c - p) / p * 100).toFixed(1) : "0";
const tl = { morning: "早晨", noon: "中午", evening: "晚上", bedtime: "睡前" };

// ============================================================================
// 主组件
// ============================================================================
export default function AIAssistantV4() {
  const [suppExp, setSuppExp] = useState(false);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState([]);
  const g = D.garmin;
  const hour = new Date().getHours();
  const hi = hour < 6 ? "夜深了" : hour < 11 ? "早上好" : hour < 14 ? "中午好" : hour < 18 ? "下午好" : "晚上好";
  const sc = D.score >= 80 ? "#22c55e" : D.score >= 60 ? "#f59e0b" : "#ef4444";

  const suppFlat = ["morning","noon","evening","bedtime"].flatMap(t => D.supplements.filter(s => s.timing === t).map(s => ({...s, _t: t})));
  const suppDone = D.supplements.filter(s => s.taken).length;
  const suppAll = D.supplements.length;
  const suppVis = suppExp ? suppFlat : suppFlat.slice(0, 6);

  const stepsPct = Math.min(100, Math.round((g.steps / 8000) * 100));
  const waterPct = Math.min(100, Math.round((D.water.ml / D.water.goal) * 100));
  const suppPct = Math.round((suppDone / suppAll) * 100);

  const alerts = useMemo(() => {
    const a = [];
    const rem = suppAll - suppDone;
    if (rem > 0) a.push({ icon: "💊", text: `${rem}项补剂待服用`, bg: "#f5f3ff", bd: "#e9d5ff", btn: "去打卡" });
    if (g.spo2 < 95) a.push({ icon: "🫁", text: `血氧 ${g.spo2}% 低于正常值(95%)，注意休息`, bg: "#fef2f2", bd: "#fecaca", btn: "查看" });
    return a;
  }, []);

  const send = (t) => { if (!t?.trim()) return; setMsgs(p => [...p, { r: "user", c: t }]); setInput(""); };
  const isChat = msgs.length > 0;

  return (
    <div style={{ fontFamily: F, background: "#f7f8fa", minHeight: "100vh" }}>
      {/* ── HEADER ── */}
      <header style={{ position: "sticky", top: 0, zIndex: 50, background: "rgba(255,255,255,.92)", backdropFilter: "blur(16px)", borderBottom: "1px solid #f0f0f0" }}>
        <div style={{ maxWidth: 820, margin: "0 auto", padding: "0 16px", height: 48, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: 8, background: "linear-gradient(135deg,#10b981,#059669)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 700 }}>H</div>
            <span style={{ fontWeight: 600, fontSize: 14, color: "#111" }}>智能助理</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <button style={{ color: "#aaa", background: "none", border: "none", cursor: "pointer" }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
            <button style={{ color: "#aaa", background: "none", border: "none", cursor: "pointer", fontSize: 18 }}>+</button>
            <span style={{ fontSize: 12, color: "#888" }}>功能</span>
            <div style={{ width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg,#a78bfa,#7c3aed)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 11, fontWeight: 600 }}>b</div>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 820, margin: "0 auto", padding: "12px 12px 130px" }}>
        {!isChat ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

            {/* ━━━━━━ 1. STATUS HERO ━━━━━━ */}
            <div style={{ borderRadius: 18, padding: "18px 20px 16px", background: "linear-gradient(135deg, #064e3b 0%, #065f46 40%, #047857 100%)", position: "relative", overflow: "hidden" }}>
              <div style={{ position: "absolute", top: -50, right: -20, width: 180, height: 180, borderRadius: "50%", background: "radial-gradient(circle, rgba(34,197,94,0.2), transparent 70%)" }} />
              <div style={{ position: "relative", zIndex: 1 }}>
                {/* Row 1: Greeting + Refresh */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                  <div>
                    <h1 style={{ fontSize: 17, fontWeight: 600, color: "#fff", margin: 0 }}>{hi}，{D.user}</h1>
                    <div style={{ fontSize: 11, color: "rgba(255,255,255,0.4)", marginTop: 2 }}>{D.date}</div>
                  </div>
                  <button style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", background: "rgba(255,255,255,0.08)", border: "none", borderRadius: 8, padding: "5px 10px", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeLinecap="round" strokeLinejoin="round"/></svg>
                    刷新
                  </button>
                </div>

                {/* Row 2: Score + Insight */}
                <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 10 }}>
                  <div style={{ position: "relative", flexShrink: 0 }}>
                    <Ring val={D.score} size={76} sw={6} color={sc} />
                    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                      <span style={{ fontSize: 22, fontWeight: 700, color: "#fff", lineHeight: 1 }}>{D.score}</span>
                      <span style={{ fontSize: 9, color: "rgba(255,255,255,0.4)" }}>健康分</span>
                    </div>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "inline-flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                      <span style={{ fontSize: 11, fontWeight: 600, color: "#fff", background: sc, padding: "2px 8px", borderRadius: 6 }}>
                        {D.score >= 80 ? "状态优秀" : D.score >= 60 ? "需要关注" : "状态较差"}
                      </span>
                    </div>
                    <p style={{ fontSize: 11, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, margin: 0, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {D.insight}
                    </p>
                  </div>
                </div>

                {/* Row 3: Dimension bars — horizontal labeled */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 6, marginTop: 14 }}>
                  {Object.entries(D.dims).map(([k, v]) => {
                    const bc = v >= 70 ? "#22c55e" : v >= 40 ? "#f59e0b" : "#ef4444";
                    return (
                      <div key={k} style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 9, color: "rgba(255,255,255,0.35)", marginBottom: 3 }}>{dimMap[k].n}</div>
                        <div style={{ height: 4, borderRadius: 4, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                          <div style={{ height: "100%", borderRadius: 4, background: bc, width: `${v}%`, transition: "width 0.8s" }} />
                        </div>
                        <div style={{ fontSize: 10, fontWeight: 600, color: bc, marginTop: 3 }}>{v}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* ━━━━━━ 2. ALERTS ━━━━━━ */}
            {alerts.map((a, i) => (
              <div key={i} style={{ borderRadius: 12, padding: "10px 14px", display: "flex", alignItems: "center", gap: 10, background: a.bg, border: `1px solid ${a.bd}` }}>
                <span style={{ fontSize: 15 }}>{a.icon}</span>
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500, color: "#374151" }}>{a.text}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#059669", background: "#d1fae5", padding: "4px 10px", borderRadius: 8, cursor: "pointer" }}>{a.btn}</span>
              </div>
            ))}

            {/* ━━━━━━ 3. BODY METRICS ━━━━━━ */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
              {[
                { icon: "❤️", v: g.hr, u: "bpm", l: "心率", ok: v => v <= 80 },
                { icon: "🔋", v: g.battery, u: "", l: "电量", sub: `当前${g.batteryLow}`, ok: v => v >= 50 },
                { icon: "😴", v: g.sleepScore, u: "分", l: "睡眠", sub: `${g.sleepH}h${g.sleepM}m`, ok: v => v >= 70 },
                { icon: "😌", v: g.stress, u: "", l: "压力", ok: v => v <= 40 },
              ].map(m => (
                <div key={m.l} style={{ ...card, padding: "12px 8px", textAlign: "center", background: m.v != null && !m.ok(m.v) ? "#fffbeb" : "#fff" }}>
                  <span style={{ fontSize: 16 }}>{m.icon}</span>
                  <div style={{ fontSize: 24, fontWeight: 700, color: "#111", marginTop: 2, lineHeight: 1.2 }}>{m.v ?? "--"}{m.u && <span style={{ fontSize: 10, color: "#aaa", marginLeft: 2 }}>{m.u}</span>}</div>
                  <div style={{ fontSize: 10, color: "#aaa", marginTop: 2 }}>{m.l}</div>
                  {m.sub && <div style={{ fontSize: 9, color: "#bbb" }}>{m.sub}</div>}
                </div>
              ))}
            </div>

            {/* ━━━━━━ 4. CONTEXT ━━━━━━ */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8 }}>
              <div style={{ ...card, background: "linear-gradient(150deg,#eef2ff,#e0f2fe)", borderColor: "#dbeafe50" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>{D.weather.city}</span><span style={{ fontSize: 11, color: "#64748b" }}>{D.weather.desc}</span></div>
                <div style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", margin: "2px 0" }}>{D.weather.temp}°<span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 400 }}> {D.weather.low}°/{D.weather.high}°</span></div>
                <div style={{ display: "flex", gap: 3, fontSize: 9 }}>
                  <span style={{ padding: "1px 4px", borderRadius: 3, background: D.weather.aqi <= 50 ? "#dcfce7" : "#fef9c3", color: D.weather.aqi <= 50 ? "#16a34a" : "#ca8a04", fontWeight: 500 }}>AQI {D.weather.aqi}</span>
                  <span style={{ padding: "1px 4px", borderRadius: 3, background: "#f0fdf4", color: "#16a34a", fontWeight: 500 }}>PM2.5 {D.weather.pm25}</span>
                </div>
              </div>
              <div style={{ ...card, background: "linear-gradient(150deg,#fff7ed,#fefce8)", borderColor: "#fed7aa40" }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}><span style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>饮食</span><span style={{ fontSize: 10, color: "#aaa" }}>{D.diet.meals}餐</span></div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", margin: "2px 0" }}>{D.diet.cal}<span style={{ fontSize: 10, color: "#aaa", fontWeight: 400 }}> kcal</span></div>
                <div style={{ fontSize: 9, color: "#78716c" }}><b style={{ color: "#ef4444" }}>{D.diet.protein}g</b>蛋白 <b style={{ color: "#f59e0b" }}>{D.diet.carbs}g</b>碳水 <b style={{ color: "#22c55e" }}>{D.diet.fat}g</b>脂肪</div>
              </div>
              <div style={{ ...card, background: "linear-gradient(150deg,#faf5ff,#fdf4ff)", borderColor: "#e9d5ff40" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 4 }}>👃 鼻炎</div>
                <div style={{ display: "flex", gap: 12 }}>
                  <div><div style={{ fontSize: 22, fontWeight: 700, color: "#0f172a" }}>{D.rhinitis.sneeze}</div><div style={{ fontSize: 9, color: "#aaa" }}>喷嚏</div></div>
                  <div><div style={{ fontSize: 22, fontWeight: 700, color: "#0f172a" }}>{D.rhinitis.wash}<span style={{ fontSize: 11, color: "#aaa" }}>/2</span></div><div style={{ fontSize: 9, color: "#aaa" }}>洗鼻</div></div>
                </div>
              </div>
              <div style={{ ...card, background: "linear-gradient(150deg,#f0fdf4,#ecfdf5)", borderColor: "#bbf7d040" }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 4 }}>⚖️ 体重</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: "#0f172a" }}>{D.weight.current}<span style={{ fontSize: 10, color: "#aaa", fontWeight: 400 }}> kg</span></div>
                <div style={{ fontSize: 10, fontWeight: 500, color: D.weight.change <= 0 ? "#16a34a" : "#ef4444" }}>30天 {D.weight.change > 0 ? "+" : ""}{D.weight.change}kg</div>
              </div>
            </div>

            {/* ━━━━━━ 5. PROGRESS RINGS ━━━━━━ */}
            <div style={{ ...card, padding: "14px 16px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr" }}>
                {[
                  { p: stepsPct, c: "#6366f1", l: "步数", d: g.steps.toLocaleString(), s: "/8,000" },
                  { p: waterPct, c: "#3b82f6", l: "饮水", d: String(D.water.ml), s: `/${D.water.goal}ml` },
                  { p: suppPct, c: "#8b5cf6", l: "补剂", d: `${suppDone}/${suppAll}`, s: "" },
                ].map(r => (
                  <div key={r.l} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                    <div style={{ position: "relative", width: 48, height: 48 }}>
                      <MiniRing pct={r.p} color={r.c} />
                      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#374151" }}>{r.p}%</div>
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#1f2937", marginTop: 4 }}>{r.d}</span>
                    {r.s && <span style={{ fontSize: 10, color: "#aaa" }}>{r.s}</span>}
                    <span style={{ fontSize: 10, color: "#aaa" }}>{r.l}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* ━━━━━━ 6. SLEEP ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>🌙 昨夜睡眠详情</span>
                <span style={{ fontSize: 11, color: "#aaa" }}>{g.sleepH}h{g.sleepM}m</span>
              </div>
              <div style={{ display: "flex", height: 12, borderRadius: 6, overflow: "hidden", gap: 1 }}>
                <div style={{ width: `${(g.deep/(g.deep+g.rem+g.light))*100}%`, background: "#312e81", borderRadius: "6px 0 0 6px" }} />
                <div style={{ width: `${(g.rem/(g.deep+g.rem+g.light))*100}%`, background: "#818cf8" }} />
                <div style={{ width: `${(g.light/(g.deep+g.rem+g.light))*100}%`, background: "#c7d2fe", borderRadius: "0 6px 6px 0" }} />
              </div>
              <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 11, color: "#6b7280" }}>
                <span>● <span style={{ color: "#312e81" }}>深睡</span> {(g.deep/60).toFixed(1)}h</span>
                <span>● <span style={{ color: "#818cf8" }}>REM</span> {Math.round(g.rem)}m</span>
                <span>● <span style={{ color: "#c7d2fe" }}>浅睡</span> {(g.light/60).toFixed(1)}h</span>
              </div>
              <div style={{ display: "flex", gap: 16, marginTop: 10, paddingTop: 8, borderTop: "1px solid #f5f5f5", alignItems: "baseline" }}>
                <div><span style={{ fontSize: 20, fontWeight: 700 }}>{g.sleepScore}</span><span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>睡眠分</span></div>
                <div><span style={{ fontSize: 16, fontWeight: 600, color: "#374151" }}>{g.hrv}</span><span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>HRV ms</span></div>
                <div><span style={{ fontSize: 16, fontWeight: 600, color: g.spo2 < 95 ? "#ef4444" : "#374151" }}>{g.spo2}</span><span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>SpO2 %</span></div>
              </div>
            </div>

            {/* ━━━━━━ 7. BP ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>🩺 血压（近30天均值）</span>
                <span style={{ fontSize: 10, color: "#aaa" }}>{D.bp.count}次记录</span>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 26, fontWeight: 700, color: "#111" }}>{D.bp.sys}/{D.bp.dia}</span>
                <span style={{ fontSize: 12, color: "#6b7280" }}>mmHg</span>
                <span style={{ fontSize: 12, color: "#6b7280" }}>脉搏 {D.bp.pulse} bpm</span>
                <span style={{ fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 6, background: "#dcfce7", color: "#16a34a" }}>{D.bp.label}</span>
              </div>
            </div>

            {/* ━━━━━━ 8. MED EXAM TRENDS ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>🔬 体检指标趋势</span>
                <span style={{ fontSize: 11, color: "#059669", cursor: "pointer" }}>查看详情</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }}>
                {D.medExams.map((m, i) => (
                  <div key={i} style={{ padding: 10, borderRadius: 10, background: "#f9fafb" }}>
                    <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>{m.name}</div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                      <span style={{ fontSize: 18, fontWeight: 700, color: "#111" }}>{m.val}</span>
                      <span style={{ fontSize: 9, color: "#aaa" }}>{m.unit}</span>
                    </div>
                    <Spark data={m.trend} color={m.good ? "#22c55e" : "#f59e0b"} w={70} h={22} />
                    <div style={{ fontSize: 10, fontWeight: 500, color: m.good ? "#16a34a" : "#f59e0b", marginTop: 2 }}>
                      {m.change > 0 ? "↑" : "↓"} {Math.abs(m.change)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* ━━━━━━ 9. MEDICATION ━━━━━━ */}
            {D.meds.length > 0 && (
              <div style={{ ...card }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>💊 今日用药</span>
                  <span style={{ fontSize: 11, color: "#aaa" }}>{D.meds.filter(m=>m.taken).length}/{D.meds.length}</span>
                </div>
                {D.meds.map((m, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: "#059669", background: "#d1fae5", padding: "2px 8px", borderRadius: 6 }}>{m.name}({m.dosage})</span>
                    {m.taken && <span style={{ fontSize: 10, color: "#aaa" }}>✓ 已服用</span>}
                  </div>
                ))}
              </div>
            )}

            {/* ━━━━━━ 10. ACTIVITY + WORKOUTS (merged) ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>🏃 今日活动</span>
                <span style={{ fontSize: 11, color: "#059669", cursor: "pointer" }}>查看全部</span>
              </div>
              {/* Activity summary */}
              <div style={{ display: "flex", gap: 16, marginBottom: 10, paddingBottom: 10, borderBottom: "1px solid #f5f5f5" }}>
                <div><span style={{ fontSize: 22, fontWeight: 700, color: "#111" }}>{g.activeMin}</span><span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>活动分钟</span></div>
                <div><span style={{ fontSize: 22, fontWeight: 700, color: "#111" }}>{g.activeCal}</span><span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>卡路里</span></div>
                <div><span style={{ fontSize: 22, fontWeight: 700, color: "#111" }}>{g.floors}</span><span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>层楼梯</span></div>
              </div>
              {/* Recent workouts */}
              {D.workouts.map((w, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderTop: i > 0 ? "1px solid #fafafa" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 14 }}>🏃</span>
                    <div>
                      <span style={{ fontSize: 13, fontWeight: 500, color: "#374151" }}>{w.sub}</span>
                    </div>
                  </div>
                  <div style={{ fontSize: 11, color: "#6b7280", textAlign: "right" }}>
                    {w.dist}km {w.dur}min <span style={{ color: "#f59e0b", fontWeight: 500 }}>{w.cal}kcal</span>
                    <div style={{ fontSize: 9, color: "#d1d5db" }}>{w.date}</div>
                  </div>
                </div>
              ))}
            </div>

            {/* ━━━━━━ 11. TRENDS ━━━━━━ */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {[
                { icon: "❤️", l: "心率", ...D.trends.hr, c: "#ef4444", gd: true },
                { icon: "💓", l: "HRV", ...D.trends.hrv, c: "#6366f1", gd: false },
                { icon: "😤", l: "压力", ...D.trends.stress, c: "#f59e0b", gd: true },
                { icon: "🚶", l: "步数", ...D.trends.steps, c: "#22c55e", gd: false },
              ].map(t => {
                const ca = Math.round(avg(t.data)), pa = Math.round(avg(t.prev));
                const ch = Number(pct(ca, pa));
                const ok = t.gd ? ch <= 0 : ch >= 0;
                return (
                  <div key={t.l} style={{ ...card, padding: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                      <span style={{ fontSize: 12, fontWeight: 500, color: "#4b5563" }}>{t.icon} {t.l} 7日</span>
                      <span style={{ fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 8, background: ok ? "#f0fdf4" : "#fef2f2", color: ok ? "#16a34a" : "#ef4444" }}>{ch >= 0 ? "+" : ""}{ch}%</span>
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "#111", marginBottom: 4 }}>{ca}<span style={{ fontSize: 10, color: "#aaa", marginLeft: 3 }}>{t.unit}</span></div>
                    <Spark data={t.data} color={t.c} />
                  </div>
                );
              })}
            </div>

            {/* ━━━━━━ 12. SUPPLEMENTS ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}><span>💊</span><span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>今日补剂</span></div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 40, height: 4, background: "#f3f4f6", borderRadius: 4, overflow: "hidden" }}><div style={{ height: "100%", background: "#22c55e", borderRadius: 4, width: `${(suppDone/suppAll)*100}%` }} /></div>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#6b7280" }}>{suppDone}/{suppAll}</span>
                </div>
              </div>
              {(() => { let lt = ""; return suppVis.map((s, i) => { const h = s._t !== lt; lt = s._t; return (
                <div key={i}>
                  {h && <div style={{ fontSize: 9, fontWeight: 500, color: "#aaa", margin: "6px 0 2px", textTransform: "uppercase", letterSpacing: 1.5 }}>{tl[s._t]}</div>}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 0" }}>
                    <div style={{ width: 14, height: 14, borderRadius: 3, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: s.taken ? "#22c55e" : "transparent", border: s.taken ? "none" : "1.5px solid #d1d5db" }}>
                      {s.taken && <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3"><path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                    </div>
                    <span style={{ flex: 1, fontSize: 12, color: s.taken ? "#aaa" : "#374151", textDecoration: s.taken ? "line-through" : "none" }}>{s.name}</span>
                    {s.dosage && <span style={{ fontSize: 10, color: "#bbb" }}>{s.dosage}</span>}
                  </div>
                </div>
              ); }); })()}
              {suppFlat.length > 6 && <button onClick={() => setSuppExp(!suppExp)} style={{ width: "100%", marginTop: 4, padding: "4px 0", fontSize: 11, color: "#059669", background: "none", border: "none", cursor: "pointer" }}>{suppExp ? "收起" : `展开全部 (${suppFlat.length})`}</button>}
            </div>

            {/* ━━━━━━ 13. QUICK RECORD ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#111", marginBottom: 8 }}>快速记录</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {D.quickRecord.map((a, i) => (
                  <button key={i} onClick={() => send(a.label)} style={{ display: "flex", alignItems: "center", gap: 4, padding: "6px 12px", borderRadius: 18, border: "1px solid #e5e7eb", background: "#fafafa", fontSize: 12, color: "#374151", cursor: "pointer" }}>
                    <span>{a.icon}</span> {a.label}
                  </button>
                ))}
              </div>
            </div>

            {/* ━━━━━━ 14. NAV GRID ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#111", marginBottom: 8 }}>健康管理</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
                {[
                  { i: "💊", l: "补剂" }, { i: "🍽️", l: "饮食" }, { i: "💧", l: "饮水" }, { i: "👃", l: "鼻炎" },
                  { i: "😊", l: "情绪" }, { i: "🏋️", l: "运动" }, { i: "📦", l: "产品库" },
                  { i: "🌙", l: "睡眠" }, { i: "⚖️", l: "体重" }, { i: "❤️", l: "心率" }, { i: "🩺", l: "血压" },
                  { i: "⌚", l: "Garmin" }, { i: "🧬", l: "基因" }, { i: "⚙️", l: "设置" },
                ].map(x => (
                  <button key={x.l} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, padding: "6px 0", borderRadius: 8, border: "none", background: "transparent", cursor: "pointer", fontSize: 9, color: "#555" }}>
                    <span style={{ fontSize: 20 }}>{x.i}</span><span>{x.l}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* ━━━━━━ 15. GOALS ━━━━━━ */}
            <div style={{ ...card }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#111" }}>🎯 目标追踪</span>
                <span style={{ fontSize: 11, color: "#059669", cursor: "pointer" }}>管理</span>
              </div>
              {D.goals.map((g, i) => {
                const p = Math.min(100, Math.round((g.cur / g.target) * 100));
                const bc = p >= 100 ? "#22c55e" : p >= 50 ? "#3b82f6" : "#f59e0b";
                return (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
                      <span style={{ color: "#374151" }}>{g.title}</span>
                      <span style={{ color: "#6b7280", fontSize: 11 }}>{g.cur}/{g.target}{g.unit}</span>
                    </div>
                    <div style={{ height: 4, background: "#f3f4f6", borderRadius: 4, overflow: "hidden" }}>
                      <div style={{ height: "100%", borderRadius: 4, background: bc, width: `${p}%`, transition: "width 0.8s" }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* ━━━━━━ 16. QUICK ASK ━━━━━━ */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {["睡眠分析","运动建议","记录饮食","AI 洞察","趋势报告"].map(q => (
                <button key={q} onClick={() => send(q)} style={{ padding: "7px 12px", borderRadius: 10, border: "1px solid #e5e7eb", background: "#fff", fontSize: 12, color: "#555", cursor: "pointer" }}>{q}</button>
              ))}
            </div>

          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <button onClick={() => setMsgs([])} style={{ alignSelf: "flex-start", fontSize: 12, color: "#059669", background: "#f0fdf4", border: "1px solid #d1fae5", borderRadius: 8, padding: "5px 12px", cursor: "pointer" }}>← 返回</button>
            {msgs.map((m, i) => (
              <div key={i} style={{ display: "flex", justifyContent: m.r === "user" ? "flex-end" : "flex-start" }}>
                <div style={{ maxWidth: "75%", borderRadius: 16, padding: "10px 14px", fontSize: 13, lineHeight: 1.7, ...(m.r === "user" ? { background: "linear-gradient(135deg,#10b981,#059669)", color: "#fff" } : { background: "#fff", border: "1px solid #eee", color: "#111" }) }}>{m.c}</div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* ── INPUT ── */}
      <div style={{ position: "fixed", bottom: 0, left: 0, right: 0, padding: "6px 12px max(10px, env(safe-area-inset-bottom))", background: "linear-gradient(transparent, #f7f8fa 25%)" }}>
        <div style={{ maxWidth: 820, margin: "0 auto", borderRadius: 14, background: "#fff", border: "1px solid #e5e7eb", boxShadow: "0 -1px 8px rgba(0,0,0,.02)", display: "flex", alignItems: "center", gap: 6, padding: "7px 10px" }}>
          <button style={{ width: 32, height: 32, borderRadius: 8, border: "none", background: "transparent", color: "#aaa", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
          <button style={{ width: 32, height: 32, borderRadius: 8, border: "none", background: "transparent", color: "#aaa", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
          <input type="text" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); send(input); } }}
            placeholder="用一句完整目标开始，例如：分析今天状态"
            style={{ flex: 1, border: "none", outline: "none", fontSize: 13, color: "#333", background: "transparent" }} />
          <button style={{ fontSize: 12, color: "#059669", background: "#f0fdf4", border: "1px solid #d1fae5", borderRadius: 8, padding: "5px 10px", cursor: "pointer", flexShrink: 0, fontWeight: 500 }}>新开对话</button>
          <button onClick={() => send(input)} disabled={!input.trim()} style={{ width: 30, height: 30, borderRadius: 8, border: "none", background: input.trim() ? "#10b981" : "#f3f4f6", color: input.trim() ? "#fff" : "#aaa", cursor: input.trim() ? "pointer" : "not-allowed", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
