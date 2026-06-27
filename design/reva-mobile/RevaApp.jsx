/* 复元 Reva — mobile app, optimized build.
   Merged + refined from the design-system UI kit. Mounted by Reva Mobile.dc.html
   via <x-import component="RevaApp" from="./RevaApp.jsx">.
   React is provided globally by the DC runtime; lucide is loaded in the DC <helmet>. */

/* ── Tokens ─────────────────────────────────────────────────── */
const C = {
  paper:'#F7F6F2', paper2:'#F1EFE8', surface:'#FFFFFF', surface2:'#FBFAF7',
  ink1:'#16201B', ink2:'#5C6660', ink3:'#8A938D', ink4:'#B7BDB7',
  line:'#E7E5DE', lineStrong:'#D7D5CC',
  green:'#1F8A5B', green600:'#176F49', green50:'#E8F2EC', green100:'#CDE6D8', greenBright:'#3AD29F',
  blue:'#2A6FDB', blue50:'#E7EEFB',
  focus:'#0F1C17', focus2:'#16271F', focusLine:'#23463A', focusInk1:'#EAF3EE', focusInk2:'#9DB3A8',
  normal:'#1F8A5B', normalBg:'#E8F2EC', normalLine:'#CDE6D8',
  caution:'#C98A1E', cautionBg:'#FBF1DD', cautionLine:'#F0DCB0',
  risk:'#D5503A', riskBg:'#FBE8E4', riskLine:'#F3CDC4',
  info:'#2A6FDB', infoBg:'#E7EEFB',
  mono:"'IBM Plex Mono', ui-monospace, monospace",
  sans:"'Manrope','Noto Sans SC',system-ui,sans-serif",
};
const STATUS = {
  normal:{c:C.normal,bg:C.normalBg,ln:C.normalLine,label:'达标'},
  caution:{c:C.caution,bg:C.cautionBg,ln:C.cautionLine,label:'注意'},
  risk:{c:C.risk,bg:C.riskBg,ln:C.riskLine,label:'偏高'},
  info:{c:C.info,bg:C.infoBg,ln:C.blue50,label:'数据'},
};
const LOGO = 'assets/logo-mark.svg';

/* ── Icon ───────────────────────────────────────────────────── */
function Icon({ name, size=22, color, style }) {
  return (
    <span style={{ fontSize:size, color, lineHeight:0, display:'inline-flex', flex:'none', ...style }}>
      <i data-lucide={name}></i>
    </span>
  );
}

/* ── Button ─────────────────────────────────────────────────── */
function Button({ children, variant='primary', size='md', icon, onClick, full, style }) {
  const base = {
    fontFamily:C.sans, fontWeight:700, border:'none', cursor:'pointer',
    display:'inline-flex', alignItems:'center', justifyContent:'center', gap:8,
    borderRadius:999, transition:'transform .12s ease, background .15s ease, box-shadow .15s',
    width: full?'100%':undefined, whiteSpace:'nowrap',
  };
  const sizes = { md:{padding:'14px 22px',fontSize:16}, sm:{padding:'9px 16px',fontSize:14}, lg:{padding:'16px 24px',fontSize:17} };
  const variants = {
    primary:{ background:C.green, color:'#fff', boxShadow:'0 6px 18px rgba(31,138,91,.28)' },
    secondary:{ background:C.surface, color:C.ink1, border:`1.5px solid ${C.lineStrong}` },
    tertiary:{ background:'transparent', color:C.green600 },
    dark:{ background:C.focus, color:C.greenBright, boxShadow:'0 8px 22px rgba(8,20,15,.28)' },
    ghost:{ background:C.green50, color:C.green600 },
  };
  const [press,setPress]=React.useState(false);
  return (
    <button onClick={onClick}
      onPointerDown={()=>setPress(true)} onPointerUp={()=>setPress(false)} onPointerLeave={()=>setPress(false)}
      style={{ ...base, ...sizes[size], ...variants[variant], transform:press?'scale(0.97)':'none', ...style }}>
      {icon && <Icon name={icon} size={size==='sm'?16:18} />}{children}
    </button>
  );
}

/* ── Chip / Dot / SectionLabel / Card ───────────────────────── */
function Chip({ status='info', children, soft=true, style }) {
  const s = STATUS[status] || STATUS.info;
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', gap:6, padding:'4px 10px', borderRadius:999,
      fontFamily:C.sans, fontWeight:600, fontSize:12,
      color:s.c, background:soft?s.bg:'transparent', border:`1px solid ${s.ln}`, ...style }}>
      <span style={{ width:7, height:7, borderRadius:'50%', background:s.c }}></span>{children}
    </span>
  );
}
function Dot({ status='normal', size=9 }) {
  const s = STATUS[status] || STATUS.normal;
  return <span style={{ width:size, height:size, borderRadius:'50%', background:s.c, flex:'none', display:'inline-block' }}></span>;
}
function SectionLabel({ children, action, onAction }) {
  return (
    <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', padding:'0 4px', marginBottom:10 }}>
      <span style={{ fontFamily:C.sans, fontWeight:700, fontSize:11, letterSpacing:'.09em', textTransform:'uppercase', color:C.ink3, whiteSpace:'nowrap' }}>{children}</span>
      {action && <span onClick={onAction} style={{ fontFamily:C.sans, fontSize:13, fontWeight:600, color:C.green600, cursor:onAction?'pointer':'default', whiteSpace:'nowrap', flex:'none', paddingLeft:12 }}>{action}</span>}
    </div>
  );
}
function Card({ children, pad=18, onClick, style }) {
  const [hov,setHov]=React.useState(false);
  return (
    <div onClick={onClick}
      onPointerEnter={()=>onClick&&setHov(true)} onPointerLeave={()=>setHov(false)}
      style={{
        background:C.surface, border:`1px solid ${C.line}`, borderRadius:18,
        boxShadow: hov?'0 10px 26px rgba(20,32,27,.10)':'0 4px 16px rgba(20,32,27,.06)', padding:pad,
        transition:'box-shadow .18s ease, transform .18s ease',
        transform: hov?'translateY(-1px)':'none',
        cursor:onClick?'pointer':'default', ...style }}>
      {children}
    </div>
  );
}

/* ── Chrome: TopBar / TabBar ────────────────────────────────── */
function TopBar({ title, sub, mark=true, right, dark }) {
  return (
    <div style={{
      position:'sticky', top:0, zIndex:8, padding:'56px 20px 14px',
      background: dark ? 'rgba(15,28,23,0.82)' : 'rgba(247,246,242,0.82)',
      backdropFilter:'blur(14px)', WebkitBackdropFilter:'blur(14px)',
      borderBottom:`1px solid ${dark?'rgba(255,255,255,.06)':C.line}`,
      display:'flex', alignItems:'flex-end', justifyContent:'space-between' }}>
      <div style={{ display:'flex', alignItems:'center', gap:11 }}>
        {mark && <img src={LOGO} width="30" height="30" alt="" style={{ display:'block' }} />}
        <div>
          {sub && <div style={{ fontFamily:C.sans, fontSize:12, fontWeight:600, color:dark?C.focusInk2:C.ink3 }}>{sub}</div>}
          <div style={{ fontFamily:C.sans, fontSize:21, fontWeight:800, letterSpacing:'-.02em', color:dark?C.focusInk1:C.ink1 }}>{title}</div>
        </div>
      </div>
      {right}
    </div>
  );
}
function TabBar({ active, onChange }) {
  const tabs = [
    { id:'today', label:'今天', icon:'sun' },
    { id:'data',  label:'数据', icon:'activity' },
    { id:'agent', label:'复元', icon:'messages-square' },
    { id:'me',    label:'我的', icon:'user' },
  ];
  return (
    <div style={{
      flex:'none', display:'flex', justifyContent:'space-around', alignItems:'center',
      padding:'9px 12px 30px', background:'rgba(255,255,255,0.92)',
      backdropFilter:'blur(16px)', WebkitBackdropFilter:'blur(16px)',
      borderTop:`1px solid ${C.line}` }}>
      {tabs.map(t=>{
        const on = active===t.id;
        return (
          <button key={t.id} onClick={()=>onChange(t.id)} style={{
            background:'none', border:'none', cursor:'pointer', display:'flex', flexDirection:'column',
            alignItems:'center', gap:5, padding:'7px 16px', borderRadius:16, minWidth:56,
            transition:'background .18s ease' }}>
            <div style={{
              width:46, height:30, borderRadius:99, display:'flex', alignItems:'center', justifyContent:'center',
              background: on?C.green50:'transparent', transition:'background .2s ease' }}>
              <Icon name={t.icon} size={22} color={on?C.green:C.ink3} />
            </div>
            <span style={{ fontFamily:C.sans, fontSize:11, fontWeight:on?700:600, color:on?C.green600:C.ink3 }}>{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ── Readiness ring (optimized: gradient arc + tip node + label) ── */
function ReadinessRing({ score=86, size=110, stroke=11, dark=true }) {
  const r = (size-stroke)/2, circ = 2*Math.PI*r;
  const frac = score/100;
  const off = circ*(1-frac);
  const track = dark ? C.focusLine : C.green100;
  const gid = 'ring'+(dark?'D':'L');
  // tip node position (arc starts at top, sweeps clockwise)
  const ang = -Math.PI/2 + frac*2*Math.PI;
  const cx = size/2 + r*Math.cos(ang), cy = size/2 + r*Math.sin(ang);
  return (
    <div style={{ position:'relative', width:size, height:size, flex:'none' }}>
      <svg width={size} height={size}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={C.green}/>
            <stop offset="1" stopColor={C.greenBright}/>
          </linearGradient>
        </defs>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={`url(#${gid})`} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
          transform={`rotate(-90 ${size/2} ${size/2})`} />
        <circle cx={cx} cy={cy} r={stroke/2+1.5} fill={C.greenBright} />
      </svg>
      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:1 }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:size*0.33, lineHeight:1, color:dark?C.focusInk1:C.ink1 }}>{score}</span>
        <span style={{ fontFamily:C.mono, fontSize:9.5, letterSpacing:'.12em', color:dark?C.focusInk2:C.ink3 }}>/ 100</span>
      </div>
    </div>
  );
}

/* ── Sparkline ──────────────────────────────────────────────── */
function Sparkline({ points, color=C.green, w=200, h=44, fill=false }) {
  const min=Math.min(...points), max=Math.max(...points), pad=2;
  const xs = points.map((_,i)=> (i/(points.length-1))*(w));
  const ys = points.map(v=> h-pad - ((v-min)/((max-min)||1))*(h-2*pad));
  const d = xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  const gid='spk'+Math.round(w);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display:'block', height:h }}>
      <defs><linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor={color} stopOpacity="0.16"/><stop offset="1" stopColor={color} stopOpacity="0"/>
      </linearGradient></defs>
      {fill && <path d={`${d} L${w},${h} L0,${h} Z`} fill={`url(#${gid})`} />}
      <path d={d} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={xs[xs.length-1]} cy={ys[ys.length-1]} r="3.4" fill={color} />
      <circle cx={xs[xs.length-1]} cy={ys[ys.length-1]} r="6" fill={color} opacity="0.16" />
    </svg>
  );
}

/* ── Trend chart (optimized: gridlines + gradient + value labels) ── */
function TrendChart({ series, target, unit, w=320, h=164 }) {
  const padL=10, padR=12, padT=20, padB=24;
  const iw=w-padL-padR, ih=h-padT-padB;
  const vals=series.map(s=>s.v).concat([target]);
  const min=Math.min(...vals)*0.94, max=Math.max(...vals)*1.05;
  const X=i=> padL + (i/(series.length-1))*iw;
  const Y=v=> padT + (1-(v-min)/((max-min)||1))*ih;
  const line=series.map((s,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(s.v).toFixed(1)}`).join(' ');
  const ty=Y(target);
  const grid=[0,0.5,1];
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display:'block' }}>
      <defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stopColor={C.green} stopOpacity="0.14"/><stop offset="1" stopColor={C.green} stopOpacity="0"/>
      </linearGradient></defs>
      {/* gridlines */}
      {grid.map((g,i)=>(
        <line key={i} x1={padL} x2={w-padR} y1={padT+g*ih} y2={padT+g*ih} stroke={C.line} strokeWidth="1" />
      ))}
      {/* target band */}
      <line x1={padL} x2={w-padR} y1={ty} y2={ty} stroke={C.green} strokeWidth="1.5" strokeDasharray="4 4" opacity="0.6" />
      <text x={w-padR} y={ty-6} textAnchor="end" fontFamily={C.mono} fontSize="10" fontWeight="500" fill={C.green600}>理想 ≤ {target}</text>
      {/* area + line */}
      <path d={`${line} L${X(series.length-1)},${padT+ih} L${X(0)},${padT+ih} Z`} fill="url(#trendFill)" />
      <path d={line} fill="none" stroke={C.green} strokeWidth="2.75" strokeLinecap="round" strokeLinejoin="round" />
      {series.map((s,i)=>{
        const last=i===series.length-1;
        return (
          <g key={i}>
            {last && <circle cx={X(i)} cy={Y(s.v)} r="8" fill={C.green} opacity="0.14" />}
            <circle cx={X(i)} cy={Y(s.v)} r={last?5:3.4} fill={last?C.green:'#fff'} stroke={C.green} strokeWidth="2" />
            <text x={X(i)} y={Y(s.v)-12} textAnchor="middle" fontFamily={C.mono} fontSize="10.5" fontWeight="500"
              fill={last?C.green600:C.ink3}>{s.v.toFixed(1)}</text>
            <text x={X(i)} y={h-7} textAnchor="middle" fontFamily={C.mono} fontSize="10" fill={C.ink3}>{s.t}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ── Plan item ──────────────────────────────────────────────── */
function PlanItem({ icon, title, sub, tag, done, onToggle, last }) {
  return (
    <div onClick={onToggle} style={{
      display:'flex', alignItems:'center', gap:13, padding:'13px 16px', cursor:'pointer',
      borderBottom: last?'none':`1px solid ${C.line}`, transition:'background .15s' }}>
      <div style={{ width:38, height:38, borderRadius:11, flex:'none', display:'flex', alignItems:'center', justifyContent:'center',
        background: done?C.green50:C.paper2, color: done?C.green:C.ink2, transition:'background .2s, color .2s' }}>
        <Icon name={icon} size={19} />
      </div>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1, textDecoration:done?'line-through':'none', opacity:done?0.5:1, transition:'opacity .2s' }}>{title}</div>
        <div style={{ fontFamily:C.sans, fontSize:12.5, color:C.ink3 }}>{sub}</div>
      </div>
      {tag && !done && <span style={{ fontFamily:C.mono, fontSize:11, color:C.ink3 }}>{tag}</span>}
      <div style={{ width:24, height:24, borderRadius:'50%', flex:'none', display:'flex', alignItems:'center', justifyContent:'center',
        border: done?'none':`2px solid ${C.lineStrong}`, background: done?C.green:'transparent', transition:'background .2s, border .2s' }}>
        {done && <Icon name="check" size={15} color="#fff" />}
      </div>
    </div>
  );
}

/* ── Metric tile (optimized: delta pill) ────────────────────── */
function MetricTile({ icon, label, value, unit, delta, trend, status='normal', onClick }) {
  const s = STATUS[status]||STATUS.normal;
  return (
    <div onClick={onClick} style={{
      flex:1, background:C.surface, border:`1px solid ${C.line}`, borderRadius:16, padding:'13px 13px 12px',
      boxShadow:'0 2px 8px rgba(20,32,27,.05)', cursor:onClick?'pointer':'default', minWidth:0 }}>
      <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:9 }}>
        <Icon name={icon} size={15} color={C.ink3} />
        <span style={{ fontFamily:C.sans, fontSize:12, fontWeight:600, color:C.ink2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{label}</span>
      </div>
      <div style={{ display:'flex', alignItems:'baseline', gap:3 }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:22, color:s.c }}>{value}</span>
        {unit && <span style={{ fontFamily:C.mono, fontSize:10.5, color:C.ink3 }}>{unit}</span>}
      </div>
      {delta && (
        <div style={{ display:'inline-flex', alignItems:'center', gap:3, marginTop:6,
          fontFamily:C.mono, fontSize:10.5, fontWeight:500, color:s.c,
          background:s.bg, border:`1px solid ${s.ln}`, borderRadius:99, padding:'2px 7px' }}>
          {trend && <span>{trend}</span>}{delta}
        </div>
      )}
    </div>
  );
}

/* ── Lab row (optimized: inline range bar) ──────────────────── */
function LabRow({ status='normal', name, sub, value, unit, pos, onClick, last }) {
  const s = STATUS[status]||STATUS.normal;
  return (
    <div onClick={onClick} style={{
      display:'flex', alignItems:'center', gap:13, padding:'13px 16px', cursor:onClick?'pointer':'default',
      borderBottom: last?'none':`1px solid ${C.line}` }}>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:'flex', alignItems:'center', gap:8 }}>
          <Dot status={status} size={8} />
          <div style={{ fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1 }}>{name}</div>
        </div>
        {/* range bar */}
        {pos!=null && (
          <div style={{ position:'relative', height:5, borderRadius:99, marginTop:9, marginLeft:16,
            background:`linear-gradient(90deg, ${C.normalBg} 0 55%, ${C.cautionBg} 55% 78%, ${C.riskBg} 78% 100%)` }}>
            <div style={{ position:'absolute', top:'50%', left:`${pos*100}%`, transform:'translate(-50%,-50%)',
              width:11, height:11, borderRadius:'50%', background:s.c, border:'2px solid #fff', boxShadow:'0 1px 3px rgba(20,32,27,.25)' }}></div>
          </div>
        )}
        <div style={{ fontFamily:C.sans, fontSize:12, color:s.c, fontWeight:600, marginTop:6, marginLeft:16 }}>{sub}</div>
      </div>
      <div style={{ textAlign:'right', flex:'none' }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:19, color:s.c }}>{value}</span>
        {unit && <div style={{ fontFamily:C.mono, fontSize:10.5, color:C.ink3, marginTop:1 }}>{unit}</div>}
      </div>
      {onClick && <Icon name="chevron-right" size={18} color={C.ink4} />}
    </div>
  );
}

/* ── Chat bubble ────────────────────────────────────────────── */
function ChatBubble({ from='agent', children }) {
  const me = from==='me';
  return (
    <div style={{ display:'flex', justifyContent:me?'flex-end':'flex-start', marginBottom:12 }}>
      <div style={{
        maxWidth:'82%', padding:'11px 15px', borderRadius:18,
        borderBottomRightRadius:me?5:18, borderBottomLeftRadius:me?18:5,
        background: me?C.green:C.surface, color: me?'#fff':C.ink1,
        border: me?'none':`1px solid ${C.line}`, boxShadow: me?'0 4px 14px rgba(31,138,91,.22)':'0 2px 8px rgba(20,32,27,.05)',
        fontFamily:C.sans, fontSize:15, lineHeight:1.55 }}>
        {children}
      </div>
    </div>
  );
}

/* ── Day progress ───────────────────────────────────────────── */
function DayProgress({ day=23, total=90 }) {
  const pct = Math.round(day/total*100);
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:8 }}>
        <span style={{ fontFamily:C.sans, fontSize:13.5, fontWeight:700, color:C.ink1, whiteSpace:'nowrap' }}>90 天主动管理</span>
        <span style={{ fontFamily:C.mono, fontSize:13, color:C.ink2, whiteSpace:'nowrap', flex:'none', paddingLeft:12 }}>第 {day} / {total} 天</span>
      </div>
      <div style={{ height:8, borderRadius:99, background:C.paper2, overflow:'hidden' }}>
        <div style={{ height:'100%', width:pct+'%', borderRadius:99, background:`linear-gradient(90deg,${C.green},${C.greenBright})` }}></div>
      </div>
    </div>
  );
}

/* ── Mini progress bar (for section headers) ────────────────── */
function MiniBar({ pct, w=54 }) {
  return (
    <div style={{ width:w, height:6, borderRadius:99, background:C.paper2, overflow:'hidden', display:'inline-block', verticalAlign:'middle' }}>
      <div style={{ height:'100%', width:pct+'%', borderRadius:99, background:C.green, transition:'width .5s ease' }}></div>
    </div>
  );
}

/* ── Data ───────────────────────────────────────────────────── */
const LABS = [
  { id:'ldl',  status:'risk',    name:'低密度脂蛋白 LDL‑C', sub:'偏高 · 优先处理', value:'3.8', unit:'mmol/L', pos:0.86 },
  { id:'glu',  status:'caution', name:'空腹血糖',            sub:'临界 · 注意',      value:'6.3', unit:'mmol/L', pos:0.64 },
  { id:'bmi',  status:'caution', name:'体重指数 BMI',        sub:'偏高 · 注意',      value:'26.4', unit:'',      pos:0.7 },
  { id:'bp',   status:'normal',  name:'血压',                sub:'达标',            value:'122/78', unit:'mmHg', pos:0.32 },
  { id:'hdl',  status:'normal',  name:'高密度脂蛋白 HDL‑C',  sub:'达标',            value:'1.3', unit:'mmol/L', pos:0.28 },
];

/* ── Onboarding ─────────────────────────────────────────────── */
function OnboardingFlow({ onDone }) {
  const [step,setStep] = React.useState(0);
  const Dots = () => (
    <div style={{ display:'flex', gap:7, justifyContent:'center' }}>
      {[0,1,2].map(i=>(
        <span key={i} style={{ width:i===step?22:7, height:7, borderRadius:99, background:i===step?C.green:C.line, transition:'width .3s, background .3s' }}></span>
      ))}
    </div>
  );
  const Shell = ({ children, cta, onCta, sub }) => (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', padding:'72px 24px 40px', boxSizing:'border-box', background:C.paper }}>
      <div style={{ flex:1, display:'flex', flexDirection:'column' }}>{children}</div>
      <div style={{ display:'flex', flexDirection:'column', gap:18 }}>
        <Dots/>
        <Button size="lg" full onClick={onCta}>{cta}</Button>
        {sub && <div style={{ textAlign:'center', fontFamily:C.sans, fontSize:12.5, color:C.ink3 }}>{sub}</div>}
      </div>
    </div>
  );

  if (step===0) return (
    <Shell cta="开始" onCta={()=>setStep(1)} sub="已有 12,000+ 体检用户在复元管理健康">
      <div style={{ flex:1, display:'flex', flexDirection:'column', justifyContent:'center', gap:24 }}>
        <div style={{ width:72, height:72, borderRadius:22, background:C.focus, display:'flex', alignItems:'center', justifyContent:'center', boxShadow:'0 14px 36px rgba(8,20,15,.3)' }}>
          <img src="assets/logo-mark-white.svg" width="40" height="40" alt="" />
        </div>
        <div>
          <div style={{ fontFamily:C.sans, fontWeight:800, fontSize:34, lineHeight:1.15, letterSpacing:'-.02em', color:C.ink1 }}>体检之后，<br/>主动健康的 90 天。</div>
          <div style={{ fontFamily:C.sans, fontSize:16, lineHeight:1.6, color:C.ink2, marginTop:16 }}>复元把你的体检异常项，变成每天可执行的小计划，再用手环和复查数据验证它真的在改善。</div>
        </div>
      </div>
    </Shell>
  );

  if (step===1) return (
    <Shell cta="继续" onCta={()=>setStep(2)} sub="支持三甲医院、美年、爱康等常见报告格式">
      <div style={{ paddingTop:8 }}>
        <Chip status="info">第 1 步</Chip>
        <div style={{ fontFamily:C.sans, fontWeight:800, fontSize:26, color:C.ink1, margin:'14px 0 6px', letterSpacing:'-.01em' }}>导入你的体检报告</div>
        <div style={{ fontFamily:C.sans, fontSize:15, color:C.ink2, lineHeight:1.55, marginBottom:20 }}>复元会自动识别异常项，并按心代谢风险排序。</div>
        <Card pad={0}>
          <div style={{ padding:'14px 16px', borderBottom:`1px solid ${C.line}`, display:'flex', alignItems:'center', gap:10 }}>
            <Icon name="file-text" size={18} color={C.ink3}/>
            <span style={{ fontFamily:C.sans, fontWeight:600, fontSize:14, color:C.ink1 }}>体检报告_2026.pdf</span>
            <Chip status="normal" style={{ marginLeft:'auto' }}>已解析</Chip>
          </div>
          {LABS.slice(0,3).map((l,i)=>(
            <LabRow key={l.id} {...l} pos={null} last={i===2} />
          ))}
        </Card>
        <div style={{ display:'flex', gap:6, alignItems:'center', justifyContent:'center', marginTop:16, color:C.ink3, fontFamily:C.sans, fontSize:12.5 }}>
          <Icon name="lock" size={13}/> 数据加密存储，仅你可见
        </div>
      </div>
    </Shell>
  );

  return (
    <Shell cta="进入复元" onCta={onDone} sub="稍后也可以在「我的」里连接">
      <div style={{ paddingTop:8 }}>
        <Chip status="info">第 2 步</Chip>
        <div style={{ fontFamily:C.sans, fontWeight:800, fontSize:26, color:C.ink1, margin:'14px 0 6px', letterSpacing:'-.01em' }}>连接你的穿戴设备</div>
        <div style={{ fontFamily:C.sans, fontSize:15, color:C.ink2, lineHeight:1.55, marginBottom:20 }}>用真实的心率、睡眠、步数校准计划，并验证改善。</div>
        <Card pad={0}>
          {[['watch','Apple Watch','已连接 · 实时同步',true],['activity','华为运动健康','点击连接',false],['gauge','Garmin Connect','点击连接',false]].map(([ic,nm,sub,on],i)=>(
            <div key={nm} style={{ display:'flex', alignItems:'center', gap:13, padding:'15px 16px', borderBottom:i<2?`1px solid ${C.line}`:'none' }}>
              <div style={{ width:38, height:38, borderRadius:11, background:on?C.green50:C.paper2, color:on?C.green:C.ink2, display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }}><Icon name={ic} size={19}/></div>
              <div style={{ flex:1 }}>
                <div style={{ fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1 }}>{nm}</div>
                <div style={{ fontFamily:C.sans, fontSize:12.5, color:on?C.green:C.ink3 }}>{sub}</div>
              </div>
              {on ? <Icon name="check-circle-2" size={22} color={C.green}/> : <Button variant="ghost" size="sm">连接</Button>}
            </div>
          ))}
        </Card>
      </div>
    </Shell>
  );
}

/* ── Air quality (today + tomorrow) ─────────────────────────── */
function AirCol({ day, aqi, level, status, advice, last }) {
  const s = STATUS[status]||STATUS.normal;
  return (
    <div style={{ flex:1, padding:'13px 16px', borderRight: last?'none':`1px solid ${C.line}`, minWidth:0 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:7 }}>
        <span style={{ fontFamily:C.sans, fontSize:12.5, fontWeight:600, color:C.ink2 }}>{day}</span>
        <Chip status={status}>{level}</Chip>
      </div>
      <div style={{ display:'flex', alignItems:'baseline', gap:4 }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:26, lineHeight:1, color:s.c }}>{aqi}</span>
        <span style={{ fontFamily:C.mono, fontSize:10.5, color:C.ink3 }}>AQI</span>
      </div>
      <div style={{ fontFamily:C.sans, fontSize:12.5, color:C.ink2, marginTop:6, lineHeight:1.45 }}>{advice}</div>
    </div>
  );
}
function AirQuality(){
  return (
    <div>
      <SectionLabel action="朝阳区 · 实时">今明空气</SectionLabel>
      <Card pad={0}>
        <div style={{ display:'flex' }}>
          <AirCol day="今天" aqi="62" level="良" status="normal" advice="空气不错，适合户外快走、骑行" />
          <AirCol day="明天" aqi="118" level="轻度污染" status="caution" advice="改室内运动，外出戴口罩" last />
        </div>
      </Card>
    </div>
  );
}

/* ── Today ──────────────────────────────────────────────────── */
function TodayScreen({ planDone, togglePlan, goRisk }) {
  const plan = [
    { id:'walk', icon:'footprints', title:'餐后散步 20 分钟', sub:'帮助餐后血糖回落', tag:'2 次' },
    { id:'meal', icon:'utensils',   title:'午餐用全谷物替换精米', sub:'降低 LDL‑C 的关键一步' },
    { id:'med',  icon:'pill',       title:'记录今日血压', sub:'晨起静坐 5 分钟后测量' },
    { id:'sleep',icon:'moon',       title:'23:30 前入睡', sub:'昨晚睡眠 6h12m，略偏少' },
  ];
  const doneCount = plan.filter(p=>planDone[p.id]).length;
  const pct = Math.round(doneCount/plan.length*100);
  const heroStats = [
    { k:'静息心率', v:'56', u:'bpm', d:'↓ 4' },
    { k:'睡眠',     v:'6h12', u:'', d:'略短' },
    { k:'HRV',     v:'48', u:'ms', d:'↑ 平稳' },
  ];
  return (
    <React.Fragment>
      <TopBar sub="晚上好 · 5月18日 周一" title="子衡，今天还差一点" right={
        <div style={{ width:40, height:40, borderRadius:'50%', background:C.green50, color:C.green600, display:'flex', alignItems:'center', justifyContent:'center', fontFamily:C.sans, fontWeight:700 }}>衡</div>
      } />
      <div style={{ padding:'16px 16px 24px', display:'flex', flexDirection:'column', gap:22 }}>
        {/* hero — command center */}
        <div style={{ position:'relative', background:C.focus, borderRadius:24, padding:20, boxShadow:'0 18px 48px rgba(8,20,15,.4)', overflow:'hidden' }}>
          <div style={{ position:'absolute', top:-60, right:-40, width:180, height:180, borderRadius:'50%', background:'radial-gradient(circle, rgba(58,210,159,.18), transparent 70%)', pointerEvents:'none' }}></div>
          <div style={{ display:'flex', gap:18, alignItems:'center', position:'relative' }}>
            <ReadinessRing score={86} />
            <div style={{ flex:1 }}>
              <div style={{ fontFamily:C.mono, fontSize:11, letterSpacing:'.08em', color:C.focusInk2 }}>TODAY · 恢复就绪度</div>
              <div style={{ fontFamily:C.sans, fontWeight:700, fontSize:18, color:C.greenBright, margin:'4px 0 6px' }}>已就绪 · 适合中等强度</div>
              <div style={{ fontFamily:C.sans, fontSize:13.5, lineHeight:1.5, color:C.focusInk2 }}>静息心率比上周低 4 bpm，睡眠略短。今天可以快走或骑行 30 分钟。</div>
            </div>
          </div>
          <div style={{ display:'flex', gap:8, marginTop:18, paddingTop:16, borderTop:`1px solid ${C.focusLine}`, position:'relative' }}>
            {heroStats.map((s,i)=>(
              <div key={i} style={{ flex:1 }}>
                <div style={{ fontFamily:C.sans, fontSize:11, color:C.focusInk2, marginBottom:3 }}>{s.k}</div>
                <div style={{ display:'flex', alignItems:'baseline', gap:3 }}>
                  <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:17, color:C.focusInk1 }}>{s.v}</span>
                  {s.u && <span style={{ fontFamily:C.mono, fontSize:10, color:C.focusInk2 }}>{s.u}</span>}
                </div>
                <div style={{ fontFamily:C.mono, fontSize:10.5, color:C.greenBright, marginTop:1 }}>{s.d}</div>
              </div>
            ))}
          </div>
        </div>

        {/* air quality — today + tomorrow */}
        <AirQuality/>

        {/* plan */}
        <div>
          <SectionLabel action={<span style={{ display:'inline-flex', alignItems:'center', gap:8 }}><MiniBar pct={pct}/>{doneCount}/{plan.length}</span>}>今日计划</SectionLabel>
          <Card pad={0}>
            {plan.map((p,i)=>(
              <PlanItem key={p.id} {...p} done={!!planDone[p.id]} onToggle={()=>togglePlan(p.id)} />
            ))}
            <div style={{ padding:'12px 16px', display:'flex', alignItems:'center', gap:8, color:C.ink3, fontFamily:C.sans, fontSize:12.5 }}>
              <Icon name="sparkles" size={14} color={C.green}/> 计划每天根据你的数据自动调整
            </div>
          </Card>
        </div>

        {/* metrics */}
        <div>
          <SectionLabel>今日数据</SectionLabel>
          <div style={{ display:'flex', gap:10 }}>
            <MetricTile icon="gauge" label="血压" value="122/78" unit="mmHg" delta="达标" status="normal" />
            <MetricTile icon="droplet" label="空腹血糖" value="6.3" unit="mmol/L" delta="临界" trend="↑" status="caution" />
            <MetricTile icon="footprints" label="步数" value="7.2k" delta="目标 8k" status="info" />
          </div>
        </div>

        {/* focus item */}
        <div>
          <SectionLabel>本阶段重点</SectionLabel>
          <Card onClick={goRisk}>
            <div style={{ display:'flex', alignItems:'center', gap:12 }}>
              <div style={{ width:44, height:44, borderRadius:12, background:C.riskBg, color:C.risk, display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }}><Icon name="trending-down" size={22}/></div>
              <div style={{ flex:1 }}>
                <div style={{ fontFamily:C.sans, fontWeight:700, fontSize:15.5, color:C.ink1 }}>把 LDL‑C 降到 3.4 以下</div>
                <div style={{ fontFamily:C.sans, fontSize:13, color:C.ink2, marginTop:2 }}>3.8 → 3.1 · 12 周内可明显改善</div>
              </div>
              <Icon name="chevron-right" size={20} color={C.ink4}/>
            </div>
          </Card>
        </div>
      </div>
    </React.Fragment>
  );
}

/* ── Data ───────────────────────────────────────────────────── */
function DataScreen({ goRisk }) {
  return (
    <React.Fragment>
      <TopBar sub="体检 · 2026‑04‑11" title="你的数据" />
      <div style={{ padding:'16px 16px 24px', display:'flex', flexDirection:'column', gap:22 }}>
        <Card><DayProgress day={23} total={90} /></Card>

        <div>
          <SectionLabel action="5 项异常">体检异常项</SectionLabel>
          <Card pad={0}>
            {LABS.map((l,i)=>(
              <LabRow key={l.id} {...l} onClick={l.id==='ldl'?goRisk:undefined} last={i===LABS.length-1} />
            ))}
          </Card>
        </div>

        <div>
          <SectionLabel action="过去 7 天">手环数据</SectionLabel>
          <Card>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:6 }}>
              <span style={{ fontFamily:C.sans, fontWeight:600, fontSize:14, color:C.ink1 }}>静息心率</span>
              <span style={{ fontFamily:C.mono, fontSize:20, fontWeight:500, color:C.normal }}>58 <span style={{ fontSize:11, color:C.ink3 }}>bpm</span></span>
            </div>
            <Sparkline points={[64,62,63,60,61,59,58]} fill />
            <div style={{ fontFamily:C.sans, fontSize:12.5, color:C.ink3, marginTop:4 }}>↓ 4 bpm，恢复在改善</div>
          </Card>
          <div style={{ display:'flex', gap:10, marginTop:10 }}>
            <MetricTile icon="moon" label="睡眠" value="6h12" delta="略偏少" status="caution" />
            <MetricTile icon="activity" label="HRV" value="48" unit="ms" delta="平稳" trend="↑" status="normal" />
            <MetricTile icon="flame" label="活动" value="412" unit="kcal" delta="达标" status="normal" />
          </div>
        </div>
      </div>
    </React.Fragment>
  );
}

/* ── Risk detail (pushed) ───────────────────────────────────── */
function RiskDetailScreen({ onBack, goAgent }) {
  const series=[{t:'基线',v:3.8},{t:'4周',v:3.6},{t:'8周',v:3.4},{t:'12周',v:3.1}];
  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', background:C.paper }}>
      <div style={{ position:'sticky', top:0, zIndex:8, padding:'56px 16px 14px', background:'rgba(247,246,242,0.85)', backdropFilter:'blur(14px)', WebkitBackdropFilter:'blur(14px)', borderBottom:`1px solid ${C.line}`, display:'flex', alignItems:'center', gap:12 }}>
        <button onClick={onBack} style={{ width:38, height:38, borderRadius:'50%', border:`1px solid ${C.line}`, background:C.surface, display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer' }}><Icon name="chevron-left" size={20} color={C.ink1}/></button>
        <div>
          <div style={{ fontFamily:C.sans, fontSize:12, fontWeight:600, color:C.ink3 }}>心代谢风险</div>
          <div style={{ fontFamily:C.sans, fontSize:18, fontWeight:800, color:C.ink1, letterSpacing:'-.01em' }}>低密度脂蛋白 LDL‑C</div>
        </div>
      </div>
      <div style={{ flex:1, overflow:'auto', padding:'16px 16px 28px', display:'flex', flexDirection:'column', gap:20 }}>
        <Card>
          <div style={{ display:'flex', alignItems:'flex-end', justifyContent:'space-between' }}>
            <div>
              <div style={{ fontFamily:C.mono, fontSize:12, color:C.ink3, marginBottom:4 }}>当前值</div>
              <div style={{ fontFamily:C.mono, fontWeight:500, fontSize:44, lineHeight:1, color:C.risk }}>3.8<span style={{ fontSize:16, color:C.ink3 }}> mmol/L</span></div>
            </div>
            <Chip status="risk">偏高</Chip>
          </div>
          <div style={{ fontFamily:C.sans, fontSize:14.5, lineHeight:1.6, color:C.ink2, marginTop:14 }}>
            你的 LDL‑C 是 <b style={{ color:C.ink1 }}>3.8 mmol/L</b>，理想值在 3.4 以下。它是心血管风险里最值得先处理的一项——好消息是，它对饮食和运动的反应很快。
          </div>
        </Card>

        <div>
          <SectionLabel>12 周改善预测</SectionLabel>
          <Card><TrendChart series={series} target={3.4} unit="mmol/L" /></Card>
        </div>

        <div>
          <SectionLabel>你的计划</SectionLabel>
          <Card pad={0}>
            {[['utensils','用全谷物替换精米白面','每天 1 餐'],['fish','每周 2 次深海鱼','补充 Omega‑3'],['footprints','每天 6,000 步以上','已坚持 18 天']].map(([ic,t,s],i)=>(
              <div key={t} style={{ display:'flex', alignItems:'center', gap:13, padding:'13px 16px', borderBottom:i<2?`1px solid ${C.line}`:'none' }}>
                <div style={{ width:36, height:36, borderRadius:10, background:C.green50, color:C.green, display:'flex', alignItems:'center', justifyContent:'center', flex:'none' }}><Icon name={ic} size={18}/></div>
                <div style={{ flex:1 }}><div style={{ fontFamily:C.sans, fontWeight:600, fontSize:14.5, color:C.ink1 }}>{t}</div><div style={{ fontFamily:C.sans, fontSize:12.5, color:C.ink3 }}>{s}</div></div>
              </div>
            ))}
          </Card>
        </div>

        <Button variant="dark" size="lg" full icon="messages-square" onClick={goAgent}>问复元：怎么吃能降得更快？</Button>
      </div>
    </div>
  );
}

/* ── Agent chat ─────────────────────────────────────────────── */
function AgentScreen({ messages, send }) {
  const [draft,setDraft] = React.useState('');
  const quicks = ['今天能跑步吗？','解读我的血糖','这周吃得怎么样？'];
  const scrollRef = React.useRef();
  React.useEffect(()=>{ if(scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; },[messages]);
  const submit = (text)=>{ const t=(text||draft).trim(); if(!t) return; send(t); setDraft(''); };
  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', background:C.paper }}>
      <div style={{ position:'sticky', top:0, zIndex:8, padding:'56px 20px 12px', background:'rgba(247,246,242,0.85)', backdropFilter:'blur(14px)', WebkitBackdropFilter:'blur(14px)', borderBottom:`1px solid ${C.line}`, display:'flex', alignItems:'center', gap:11 }}>
        <img src={LOGO} width="32" height="32" alt=""/>
        <div style={{ flex:1 }}>
          <div style={{ fontFamily:C.sans, fontSize:18, fontWeight:800, color:C.ink1 }}>复元</div>
          <div style={{ display:'flex', alignItems:'center', gap:5 }}><Dot status="normal" size={7}/><span style={{ fontFamily:C.sans, fontSize:12, color:C.ink2 }}>了解你的全部健康数据</span></div>
        </div>
      </div>
      <div ref={scrollRef} style={{ flex:1, overflow:'auto', padding:'18px 16px' }}>
        {messages.map((m,i)=>(<ChatBubble key={i} from={m.from}>{m.text}</ChatBubble>))}
      </div>
      <div style={{ flex:'none', padding:'10px 14px 26px', background:C.paper, borderTop:`1px solid ${C.line}` }}>
        <div style={{ display:'flex', gap:8, overflowX:'auto', paddingBottom:10 }}>
          {quicks.map(q=>(<button key={q} onClick={()=>submit(q)} style={{ flex:'none', fontFamily:C.sans, fontSize:13, fontWeight:600, color:C.green600, background:C.green50, border:`1px solid ${C.green100}`, borderRadius:999, padding:'7px 13px', cursor:'pointer', whiteSpace:'nowrap' }}>{q}</button>))}
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:10, background:C.surface, border:`1.5px solid ${C.lineStrong}`, borderRadius:999, padding:'6px 6px 6px 16px' }}>
          <input value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>e.key==='Enter'&&submit()} placeholder="问问复元…" style={{ flex:1, border:'none', outline:'none', background:'transparent', fontFamily:C.sans, fontSize:15, color:C.ink1 }} />
          <button onClick={()=>submit()} style={{ width:38, height:38, borderRadius:'50%', border:'none', background:C.green, color:'#fff', display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', flex:'none' }}><Icon name="arrow-up" size={20}/></button>
        </div>
      </div>
    </div>
  );
}

/* ── Me ─────────────────────────────────────────────────────── */
function MeScreen() {
  return (
    <React.Fragment>
      <TopBar mark={false} title="我的" />
      <div style={{ padding:'16px 16px 24px', display:'flex', flexDirection:'column', gap:20 }}>
        <Card>
          <div style={{ display:'flex', alignItems:'center', gap:14, marginBottom:16 }}>
            <div style={{ width:54, height:54, borderRadius:'50%', background:C.green50, color:C.green600, display:'flex', alignItems:'center', justifyContent:'center', fontFamily:C.sans, fontWeight:700, fontSize:22 }}>衡</div>
            <div style={{ flex:1 }}>
              <div style={{ fontFamily:C.sans, fontWeight:800, fontSize:19, color:C.ink1 }}>张子衡</div>
              <div style={{ fontFamily:C.sans, fontSize:13, color:C.ink3 }}>男 · 41 岁 · 心代谢管理中</div>
            </div>
          </div>
          <DayProgress day={23} total={90} />
        </Card>

        <div>
          <SectionLabel>已连接设备</SectionLabel>
          <Card pad={0}>
            {[['watch','Apple Watch','实时同步',true],['file-text','体检报告','2026‑04‑11',true],['activity','华为运动健康','未连接',false]].map(([ic,nm,sub,on],i)=>(
              <div key={nm} style={{ display:'flex', alignItems:'center', gap:13, padding:'14px 16px', borderBottom:i<2?`1px solid ${C.line}`:'none' }}>
                <Icon name={ic} size={19} color={C.ink2}/>
                <div style={{ flex:1 }}><div style={{ fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1 }}>{nm}</div><div style={{ fontFamily:C.sans, fontSize:12.5, color:on?C.green:C.ink3 }}>{sub}</div></div>
                {on ? <Icon name="check-circle-2" size={20} color={C.green}/> : <Button variant="ghost" size="sm">连接</Button>}
              </div>
            ))}
          </Card>
        </div>

        <div>
          <SectionLabel>设置</SectionLabel>
          <Card pad={0}>
            {[['bell','每日提醒','08:00'],['calendar-check','复查提醒','7月 11 日'],['shield','隐私与数据',''],['circle-help','帮助与反馈','']].map(([ic,nm,val],i)=>(
              <div key={nm} style={{ display:'flex', alignItems:'center', gap:13, padding:'14px 16px', borderBottom:i<3?`1px solid ${C.line}`:'none' }}>
                <Icon name={ic} size={19} color={C.ink2}/>
                <span style={{ flex:1, fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1 }}>{nm}</span>
                {val && <span style={{ fontFamily:C.mono, fontSize:13, color:C.ink3 }}>{val}</span>}
                <Icon name="chevron-right" size={18} color={C.ink4} />
              </div>
            ))}
          </Card>
        </div>
      </div>
    </React.Fragment>
  );
}

/* ── iOS device frame (trimmed) ─────────────────────────────── */
function IOSStatusBar({ dark=false, time='9:41' }) {
  const c = dark ? '#fff' : '#0F1C17';
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'21px 30px 0', boxSizing:'border-box', width:'100%' }}>
      <span style={{ fontFamily:'-apple-system,"SF Pro",system-ui', fontWeight:600, fontSize:17, color:c }}>{time}</span>
      <div style={{ display:'flex', alignItems:'center', gap:7 }}>
        <svg width="19" height="12" viewBox="0 0 19 12"><rect x="0" y="7.5" width="3.2" height="4.5" rx="0.7" fill={c}/><rect x="4.8" y="5" width="3.2" height="7" rx="0.7" fill={c}/><rect x="9.6" y="2.5" width="3.2" height="9.5" rx="0.7" fill={c}/><rect x="14.4" y="0" width="3.2" height="12" rx="0.7" fill={c}/></svg>
        <svg width="17" height="12" viewBox="0 0 17 12"><path d="M8.5 3.2C10.8 3.2 12.9 4.1 14.4 5.6L15.5 4.5C13.7 2.7 11.2 1.5 8.5 1.5C5.8 1.5 3.3 2.7 1.5 4.5L2.6 5.6C4.1 4.1 6.2 3.2 8.5 3.2Z" fill={c}/><path d="M8.5 6.8C9.9 6.8 11.1 7.3 12 8.2L13.1 7.1C11.8 5.9 10.2 5.1 8.5 5.1C6.8 5.1 5.2 5.9 3.9 7.1L5 8.2C5.9 7.3 7.1 6.8 8.5 6.8Z" fill={c}/><circle cx="8.5" cy="10.5" r="1.5" fill={c}/></svg>
        <svg width="27" height="13" viewBox="0 0 27 13"><rect x="0.5" y="0.5" width="23" height="12" rx="3.5" stroke={c} strokeOpacity="0.35" fill="none"/><rect x="2" y="2" width="20" height="9" rx="2" fill={c}/><path d="M25 4.5V8.5C25.8 8.2 26.5 7.2 26.5 6.5C26.5 5.8 25.8 4.8 25 4.5Z" fill={c} fillOpacity="0.4"/></svg>
      </div>
    </div>
  );
}
function IOSDevice({ children, width=402, height=874, dark=false }) {
  return (
    <div style={{
      width, height, borderRadius:48, overflow:'hidden', position:'relative',
      background: dark?'#000':C.paper,
      boxShadow:'0 40px 90px rgba(8,20,15,0.22), 0 0 0 1px rgba(8,20,15,0.10)',
      fontFamily:'-apple-system, system-ui, sans-serif', WebkitFontSmoothing:'antialiased' }}>
      <div style={{ position:'absolute', top:11, left:'50%', transform:'translateX(-50%)', width:126, height:37, borderRadius:24, background:'#000', zIndex:50 }} />
      <div style={{ position:'absolute', top:0, left:0, right:0, zIndex:10 }}><IOSStatusBar dark={dark} /></div>
      <div style={{ height:'100%', display:'flex', flexDirection:'column' }}>{children}</div>
      <div style={{ position:'absolute', bottom:0, left:0, right:0, zIndex:60, height:34, display:'flex', justifyContent:'center', alignItems:'flex-end', paddingBottom:8, pointerEvents:'none' }}>
        <div style={{ width:139, height:5, borderRadius:100, background: dark?'rgba(255,255,255,0.7)':'rgba(15,28,23,0.22)' }} />
      </div>
    </div>
  );
}

/* ── Agent reply ────────────────────────────────────────────── */
function revaReply(text){
  if(text.includes('跑')||text.includes('运动')||text.includes('强度'))
    return '今天恢复就绪度 86，静息心率也在下降，可以跑。建议 30 分钟轻松配速，心率控制在 130 以内，跑完记得拉伸。';
  if(text.includes('血糖')||text.includes('糖'))
    return '你的空腹血糖 6.3，属于临界偏高。关键是餐后那一段：主食换成全谷物、饭后散步 10–20 分钟，两周就能看到餐后峰值下降。';
  if(text.includes('吃')||text.includes('饮食')||text.includes('降'))
    return '想更快降 LDL‑C，三件事最有效：① 用燕麦/糙米替换精白主食；② 每周 2 次深海鱼补 Omega‑3；③ 少吃动物油和油炸。坚持 4 周通常能降 0.2–0.4。';
  return '收到。我会结合你的体检异常项和这周的手环数据来看——需要我把它拆成今天可以做的一件小事吗？';
}

/* ── App ────────────────────────────────────────────────────── */
function RevaApp({ startPhase }){
  React.useEffect(()=>{ if(window.lucide) window.lucide.createIcons({ attrs:{ 'stroke-width':1.75 } }); });

  const [phase,setPhase] = React.useState(startPhase==='app'?'app':'onboard');
  const [tab,setTab]     = React.useState('today');
  const [route,setRoute] = React.useState(null);
  const [planDone,setPlanDone] = React.useState({ walk:true });
  const [messages,setMessages] = React.useState([
    { from:'agent', text:'晚上好，子衡。今天的恢复就绪度是 86，状态不错。想聊聊计划，还是看某项指标？' },
  ]);
  const togglePlan = id => setPlanDone(d=>({ ...d, [id]:!d[id] }));
  const send = text => {
    setMessages(m=>[...m,{ from:'me', text }]);
    setTimeout(()=> setMessages(m=>[...m,{ from:'agent', text:revaReply(text) }]), 450);
  };
  const goRisk  = ()=> setRoute('risk');
  const goAgent = ()=>{ setRoute(null); setTab('agent'); };

  let body;
  if (phase==='onboard') {
    body = <OnboardingFlow onDone={()=>setPhase('app')} />;
  } else if (route==='risk') {
    body = <RiskDetailScreen onBack={()=>setRoute(null)} goAgent={goAgent} />;
  } else {
    const screen =
      tab==='today' ? <TodayScreen planDone={planDone} togglePlan={togglePlan} goRisk={goRisk} />
      : tab==='data' ? <DataScreen goRisk={goRisk} />
      : tab==='agent' ? <AgentScreen messages={messages} send={send} />
      : <MeScreen />;
    const scrolls = tab!=='agent';
    body = (
      <div style={{ height:'100%', display:'flex', flexDirection:'column', background:C.paper }}>
        {scrolls
          ? <div style={{ flex:1, overflow:'auto' }}>{screen}</div>
          : <div style={{ flex:1, minHeight:0, display:'flex' }}>{screen}</div>}
        <TabBar active={tab} onChange={setTab} />
      </div>
    );
  }

  return <IOSDevice dark={false}>{body}</IOSDevice>;
}

module.exports = { RevaApp };
