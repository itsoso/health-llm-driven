/* Reva mobile — app shell: phase + tab + route state, mounts inside IOSDevice */

function revaReply(text){
  const t=text.toLowerCase();
  if(text.includes('跑')||text.includes('运动')||text.includes('强度'))
    return '今天恢复就绪度 86，静息心率也在下降，可以跑。建议 30 分钟轻松配速，心率控制在 130 以内，跑完记得拉伸。';
  if(text.includes('血糖')||text.includes('糖'))
    return '你的空腹血糖 6.3，属于临界偏高。关键是餐后那一段：主食换成全谷物、饭后散步 10–20 分钟，两周就能看到餐后峰值下降。';
  if(text.includes('吃')||text.includes('饮食')||text.includes('降'))
    return '想更快降 LDL‑C，三件事最有效：① 用燕麦/糙米替换精白主食；② 每周 2 次深海鱼补 Omega‑3；③ 少吃动物油和油炸。坚持 4 周通常能降 0.2–0.4。';
  return '收到。我会结合你的体检异常项和这周的手环数据来看——需要我把它拆成今天可以做的一件小事吗？';
}

function RevaApp(){
  // convert all pending lucide placeholders after every render
  React.useEffect(()=>{ if(window.lucide) window.lucide.createIcons({ attrs:{ 'stroke-width':1.75 } }); });

  const [phase,setPhase] = React.useState('onboard');
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
    const scrolls = tab!=='agent'; // agent manages its own internal scroll
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

ReactDOM.render(<RevaApp/>, document.getElementById('root'));
