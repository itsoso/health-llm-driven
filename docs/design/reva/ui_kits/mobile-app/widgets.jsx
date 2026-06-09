/* Reva mobile — data widgets: rings, charts, plan rows, lab rows, chat */

function ReadinessRing({ score=86, size=104, stroke=10, dark=true, label='恢复就绪度' }) {
  const r = (size-stroke)/2, circ = 2*Math.PI*r;
  const [off,setOff] = React.useState(circ);
  React.useEffect(()=>{ const id=requestAnimationFrame(()=>setOff(circ*(1-score/100))); return ()=>cancelAnimationFrame(id); },[score,circ]);
  const track = dark ? C.focusLine : C.green100;
  const arc = dark ? C.greenBright : C.green;
  return (
    <div style={{ position:'relative', width:size, height:size, flex:'none' }}>
      <svg width={size} height={size}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={arc} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
          transform={`rotate(-90 ${size/2} ${size/2})`}
          style={{ transition:'stroke-dashoffset 1s cubic-bezier(.22,.61,.36,1)' }} />
      </svg>
      <div style={{ position:'absolute', inset:0, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center' }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:size*0.34, lineHeight:1, color:dark?C.focusInk1:C.ink1 }}>{score}</span>
      </div>
    </div>
  );
}

function Sparkline({ points, color=C.green, w=200, h=44, fill=false }) {
  const min=Math.min(...points), max=Math.max(...points), pad=2;
  const xs = points.map((_,i)=> (i/(points.length-1))*(w));
  const ys = points.map(v=> h-pad - ((v-min)/((max-min)||1))*(h-2*pad));
  const d = xs.map((x,i)=>`${i?'L':'M'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display:'block', height:h }}>
      {fill && <path d={`${d} L${w},${h} L0,${h} Z`} fill={color} opacity="0.08" />}
      <path d={d} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={xs[xs.length-1]} cy={ys[ys.length-1]} r="3.2" fill={color} />
    </svg>
  );
}

/* 90-day trend with target line + measured points */
function TrendChart({ series, target, unit, w=320, h=150 }) {
  const padL=8, padR=8, padT=14, padB=22;
  const iw=w-padL-padR, ih=h-padT-padB;
  const vals=series.map(s=>s.v).concat([target]);
  const min=Math.min(...vals)*0.96, max=Math.max(...vals)*1.04;
  const X=i=> padL + (i/(series.length-1))*iw;
  const Y=v=> padT + (1-(v-min)/((max-min)||1))*ih;
  const line=series.map((s,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(s.v).toFixed(1)}`).join(' ');
  const ty=Y(target);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display:'block' }}>
      {/* target band */}
      <line x1={padL} x2={w-padR} y1={ty} y2={ty} stroke={C.green} strokeWidth="1.5" strokeDasharray="4 4" opacity="0.55" />
      <text x={w-padR} y={ty-5} textAnchor="end" fontFamily={C.mono} fontSize="10" fill={C.green600}>理想 ≤ {target}</text>
      {/* area + line */}
      <path d={`${line} L${X(series.length-1)},${padT+ih} L${X(0)},${padT+ih} Z`} fill={C.green} opacity="0.06" />
      <path d={line} fill="none" stroke={C.green} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {series.map((s,i)=>(
        <g key={i}>
          <circle cx={X(i)} cy={Y(s.v)} r={i===series.length-1?4.5:3} fill={i===series.length-1?C.green:'#fff'} stroke={C.green} strokeWidth="2" />
          <text x={X(i)} y={h-6} textAnchor="middle" fontFamily={C.mono} fontSize="10" fill={C.ink3}>{s.t}</text>
        </g>
      ))}
    </svg>
  );
}

function PlanItem({ icon, title, sub, tag, done, onToggle }) {
  return (
    <div onClick={onToggle} style={{
      display:'flex', alignItems:'center', gap:13, padding:'13px 16px', cursor:'pointer',
      borderBottom:`1px solid ${C.line}` }}>
      <div style={{ width:38, height:38, borderRadius:11, flex:'none', display:'flex', alignItems:'center', justifyContent:'center',
        background: done?C.green50:C.paper2, color: done?C.green:C.ink2 }}>
        <Icon name={icon} size={19} />
      </div>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1, textDecoration:done?'line-through':'none', opacity:done?0.55:1 }}>{title}</div>
        <div style={{ fontFamily:C.sans, fontSize:12.5, color:C.ink3 }}>{sub}</div>
      </div>
      {tag && !done && <span style={{ fontFamily:C.mono, fontSize:11, color:C.ink3 }}>{tag}</span>}
      <div style={{ width:24, height:24, borderRadius:'50%', flex:'none', display:'flex', alignItems:'center', justifyContent:'center',
        border: done?'none':`2px solid ${C.lineStrong}`, background: done?C.green:'transparent' }}>
        {done && <Icon name="check" size={15} color="#fff" />}
      </div>
    </div>
  );
}

function MetricTile({ icon, label, value, unit, delta, status='normal', onClick }) {
  const s = STATUS[status]||STATUS.normal;
  return (
    <div onClick={onClick} style={{
      flex:1, background:C.surface, border:`1px solid ${C.line}`, borderRadius:16, padding:'13px 14px',
      boxShadow:'0 2px 8px rgba(20,32,27,.05)', cursor:onClick?'pointer':'default', minWidth:0 }}>
      <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:9 }}>
        <Icon name={icon} size={16} color={C.ink3} />
        <span style={{ fontFamily:C.sans, fontSize:12, fontWeight:600, color:C.ink2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{label}</span>
      </div>
      <div style={{ display:'flex', alignItems:'baseline', gap:3 }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:22, color:s.c }}>{value}</span>
        {unit && <span style={{ fontFamily:C.mono, fontSize:11, color:C.ink3 }}>{unit}</span>}
      </div>
      {delta && <div style={{ fontFamily:C.mono, fontSize:11, color:C.ink3, marginTop:2 }}>{delta}</div>}
    </div>
  );
}

function LabRow({ status='normal', name, sub, value, unit, onClick, last }) {
  const s = STATUS[status]||STATUS.normal;
  return (
    <div onClick={onClick} style={{
      display:'flex', alignItems:'center', gap:13, padding:'14px 16px', cursor:onClick?'pointer':'default',
      borderBottom: last?'none':`1px solid ${C.line}` }}>
      <Dot status={status} />
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontFamily:C.sans, fontWeight:600, fontSize:15, color:C.ink1 }}>{name}</div>
        <div style={{ fontFamily:C.sans, fontSize:12, color:s.c, fontWeight:600 }}>{sub}</div>
      </div>
      <div style={{ textAlign:'right' }}>
        <span style={{ fontFamily:C.mono, fontWeight:500, fontSize:18, color:s.c }}>{value}</span>
        {unit && <span style={{ fontFamily:C.mono, fontSize:11, color:C.ink3 }}> {unit}</span>}
      </div>
      {onClick && <Icon name="chevron-right" size={18} color={C.ink4} />}
    </div>
  );
}

function ChatBubble({ from='agent', children }) {
  const me = from==='me';
  return (
    <div style={{ display:'flex', justifyContent:me?'flex-end':'flex-start', marginBottom:12 }}>
      <div style={{
        maxWidth:'82%', padding:'11px 15px', borderRadius:18,
        borderBottomRightRadius:me?5:18, borderBottomLeftRadius:me?18:5,
        background: me?C.green:C.surface, color: me?'#fff':C.ink1,
        border: me?'none':`1px solid ${C.line}`, boxShadow: me?'none':'0 2px 8px rgba(20,32,27,.05)',
        fontFamily:C.sans, fontSize:15, lineHeight:1.5 }}>
        {children}
      </div>
    </div>
  );
}

function DayProgress({ day=23, total=90 }) {
  const pct = Math.round(day/total*100);
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:7 }}>
        <span style={{ fontFamily:C.sans, fontSize:13, fontWeight:600, color:C.ink2, whiteSpace:'nowrap' }}>90 天主动管理</span>
        <span style={{ fontFamily:C.mono, fontSize:13, color:C.ink1, whiteSpace:'nowrap', flex:'none', paddingLeft:12 }}>第 {day} / {total} 天</span>
      </div>
      <div style={{ height:8, borderRadius:99, background:C.paper2, overflow:'hidden' }}>
        <div style={{ height:'100%', width:pct+'%', borderRadius:99, background:`linear-gradient(90deg,${C.green},${C.greenBright})` }}></div>
      </div>
    </div>
  );
}

Object.assign(window, { ReadinessRing, Sparkline, TrendChart, PlanItem, MetricTile, LabRow, ChatBubble, DayProgress });
