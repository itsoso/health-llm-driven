/* Reva mobile — primitives: tokens, Icon, Button, Chip, nav chrome
   Each <script type=text/babel> has its own scope → exported to window at end. */

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
  info:{c:C.info,bg:C.infoBg,ln:C.infoLine||C.blue50,label:'数据'},
};

/* Lucide icon — renders a placeholder that the app-root effect converts. */
function Icon({ name, size=22, color, style }) {
  return (
    <span style={{ fontSize:size, color, lineHeight:0, display:'inline-flex', flex:'none', ...style }}>
      <i data-lucide={name}></i>
    </span>
  );
}

function Button({ children, variant='primary', size='md', icon, onClick, full, style }) {
  const base = {
    fontFamily:C.sans, fontWeight:700, border:'none', cursor:'pointer',
    display:'inline-flex', alignItems:'center', justifyContent:'center', gap:8,
    borderRadius:999, transition:'transform .12s ease, background .15s ease',
    width: full?'100%':undefined, whiteSpace:'nowrap',
  };
  const sizes = { md:{padding:'14px 22px',fontSize:16}, sm:{padding:'9px 16px',fontSize:14}, lg:{padding:'16px 24px',fontSize:17} };
  const variants = {
    primary:{ background:C.green, color:'#fff', boxShadow:'0 1px 2px rgba(20,32,27,.12)' },
    secondary:{ background:C.surface, color:C.ink1, border:`1.5px solid ${C.lineStrong}` },
    tertiary:{ background:'transparent', color:C.green600 },
    dark:{ background:C.focus, color:C.greenBright },
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
      <span style={{ fontFamily:C.sans, fontWeight:600, fontSize:11, letterSpacing:'.08em', textTransform:'uppercase', color:C.ink3, whiteSpace:'nowrap' }}>{children}</span>
      {action && <span onClick={onAction} style={{ fontFamily:C.sans, fontSize:13, fontWeight:600, color:C.green600, cursor:'pointer', whiteSpace:'nowrap', flex:'none', paddingLeft:12 }}>{action}</span>}
    </div>
  );
}

function Card({ children, pad=18, onClick, style }) {
  return (
    <div onClick={onClick} style={{
      background:C.surface, border:`1px solid ${C.line}`, borderRadius:18,
      boxShadow:'0 4px 16px rgba(20,32,27,.06)', padding:pad,
      cursor:onClick?'pointer':'default', ...style }}>
      {children}
    </div>
  );
}

/* Top context bar — sits below the status island, sticky */
function TopBar({ title, sub, mark=true, right, dark }) {
  return (
    <div style={{
      position:'sticky', top:0, zIndex:8, padding:'56px 20px 14px',
      background: dark ? 'rgba(15,28,23,0.82)' : 'rgba(247,246,242,0.82)',
      backdropFilter:'blur(14px)', WebkitBackdropFilter:'blur(14px)',
      borderBottom:`1px solid ${dark?'rgba(255,255,255,.06)':C.line}`,
      display:'flex', alignItems:'flex-end', justifyContent:'space-between' }}>
      <div style={{ display:'flex', alignItems:'center', gap:11 }}>
        {mark && <img src="../../assets/logo-mark.svg" width="30" height="30" alt="" style={{ display:'block' }} />}
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
      flex:'none', display:'flex', justifyContent:'space-around', alignItems:'flex-start',
      padding:'10px 12px 30px', background:'rgba(255,255,255,0.9)',
      backdropFilter:'blur(16px)', WebkitBackdropFilter:'blur(16px)',
      borderTop:`1px solid ${C.line}` }}>
      {tabs.map(t=>{
        const on = active===t.id;
        return (
          <button key={t.id} onClick={()=>onChange(t.id)} style={{
            background:'none', border:'none', cursor:'pointer', display:'flex', flexDirection:'column',
            alignItems:'center', gap:4, padding:'4px 14px', minWidth:56 }}>
            <Icon name={t.icon} size={23} color={on?C.green:C.ink3} />
            <span style={{ fontFamily:C.sans, fontSize:11, fontWeight:on?700:600, color:on?C.green:C.ink3 }}>{t.label}</span>
          </button>
        );
      })}
    </div>
  );
}

Object.assign(window, { C, STATUS, Icon, Button, Chip, Dot, SectionLabel, Card, TopBar, TabBar });
