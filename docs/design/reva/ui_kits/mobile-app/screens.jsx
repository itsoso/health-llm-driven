/* Reva mobile — screens. Pull primitives + widgets from window. */

const LABS = [
  { id:'ldl',  status:'risk',    name:'低密度脂蛋白 LDL‑C', sub:'偏高 · 优先处理', value:'3.8', unit:'mmol/L' },
  { id:'glu',  status:'caution', name:'空腹血糖',            sub:'临界 · 注意',      value:'6.3', unit:'mmol/L' },
  { id:'bmi',  status:'caution', name:'体重指数 BMI',        sub:'偏高 · 注意',      value:'26.4', unit:'' },
  { id:'bp',   status:'normal',  name:'血压',                sub:'达标',            value:'122/78', unit:'mmHg' },
  { id:'hdl',  status:'normal',  name:'高密度脂蛋白 HDL‑C',  sub:'达标',            value:'1.3', unit:'mmol/L' },
];

/* ── Onboarding ───────────────────────────────────────────── */
function OnboardingFlow({ onDone }) {
  const [step,setStep] = React.useState(0);
  const Dots = () => (
    <div style={{ display:'flex', gap:7, justifyContent:'center' }}>
      {[0,1,2].map(i=>(
        <span key={i} style={{ width:i===step?22:7, height:7, borderRadius:99, background:i===step?C.green:C.line, transition:'width .3s' }}></span>
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
        <img src="../../assets/logo-mark.svg" width="64" height="64" alt="" />
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
            <LabRow key={l.id} {...l} last={i===2} />
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

/* ── Today ────────────────────────────────────────────────── */
function TodayScreen({ planDone, togglePlan, goRisk }) {
  const plan = [
    { id:'walk', icon:'footprints', title:'餐后散步 20 分钟', sub:'帮助餐后血糖回落', tag:'2 次' },
    { id:'meal', icon:'utensils',   title:'午餐用全谷物替换精米', sub:'降低 LDL‑C 的关键一步' },
    { id:'med',  icon:'pill',       title:'记录今日血压', sub:'晨起静坐 5 分钟后测量' },
    { id:'sleep',icon:'moon',       title:'23:30 前入睡', sub:'昨晚睡眠 6h12m，略偏少' },
  ];
  const doneCount = plan.filter(p=>planDone[p.id]).length;
  return (
    <React.Fragment>
      <TopBar sub="晚上好 · 5月18日 周一" title="子衡，今天还差一点" right={
        <div style={{ width:40, height:40, borderRadius:'50%', background:C.green50, color:C.green600, display:'flex', alignItems:'center', justifyContent:'center', fontFamily:C.sans, fontWeight:700 }}>衡</div>
      } />
      <div style={{ padding:'16px 16px 24px', display:'flex', flexDirection:'column', gap:22 }}>
        {/* hero */}
        <div style={{ background:C.focus, borderRadius:24, padding:20, boxShadow:'0 18px 48px rgba(8,20,15,.4)', display:'flex', gap:18, alignItems:'center' }}>
          <ReadinessRing score={86} />
          <div style={{ flex:1 }}>
            <div style={{ fontFamily:C.mono, fontSize:11, letterSpacing:'.08em', color:C.focusInk2 }}>TODAY · 恢复就绪度</div>
            <div style={{ fontFamily:C.sans, fontWeight:700, fontSize:18, color:C.greenBright, margin:'4px 0 6px' }}>已就绪 · 适合中等强度</div>
            <div style={{ fontFamily:C.sans, fontSize:13.5, lineHeight:1.5, color:C.focusInk2 }}>静息心率比上周低 4 bpm，睡眠略短。今天可以快走或骑行 30 分钟。</div>
          </div>
        </div>

        {/* plan */}
        <div>
          <SectionLabel action={`${doneCount}/${plan.length} 已完成`}>今日计划</SectionLabel>
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
            <MetricTile icon="droplet" label="空腹血糖" value="6.3" unit="mmol/L" delta="↑ 临界" status="caution" />
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

/* ── Data ─────────────────────────────────────────────────── */
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
            <MetricTile icon="activity" label="HRV" value="48" unit="ms" delta="↑ 平稳" status="normal" />
            <MetricTile icon="flame" label="活动" value="412" unit="kcal" delta="达标" status="normal" />
          </div>
        </div>
      </div>
    </React.Fragment>
  );
}

/* ── Risk detail (pushed) ─────────────────────────────────── */
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

/* ── Agent chat ───────────────────────────────────────────── */
function AgentScreen({ messages, send }) {
  const [draft,setDraft] = React.useState('');
  const quicks = ['今天能跑步吗？','解读我的血糖','这周吃得怎么样？'];
  const scrollRef = React.useRef();
  React.useEffect(()=>{ if(scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight; },[messages]);
  const submit = (text)=>{ const t=(text||draft).trim(); if(!t) return; send(t); setDraft(''); };
  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', background:C.paper }}>
      <div style={{ position:'sticky', top:0, zIndex:8, padding:'56px 20px 12px', background:'rgba(247,246,242,0.85)', backdropFilter:'blur(14px)', WebkitBackdropFilter:'blur(14px)', borderBottom:`1px solid ${C.line}`, display:'flex', alignItems:'center', gap:11 }}>
        <img src="../../assets/logo-mark.svg" width="32" height="32" alt=""/>
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

/* ── Me ───────────────────────────────────────────────────── */
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
                <Icon name="chevron-right" size={18} color={C.ink4}/>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </React.Fragment>
  );
}

Object.assign(window, { OnboardingFlow, TodayScreen, DataScreen, RiskDetailScreen, AgentScreen, MeScreen, LABS });
