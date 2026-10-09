import React,{useCallback,useEffect,useRef,useState} from 'react';
import {AppState,ActivityIndicator,Pressable,ScrollView,Text,TextInput,View} from 'react-native';
import {Stack,useFocusEffect,useRouter} from 'expo-router';
import {useAuth} from '../hooks/useAuth';
import {useTheme} from '../hooks/useTheme';
import {subscribeAIConsentInvalidation} from '../services/aiConsentState';
import {fetchLifeWorkspace,saveLifeWorkspace,type LifeWorkspace,type LifeData,type LifeTask} from '../services/lifeNavigation';
// Personal task identity only; this UUID is never a credential.
const taskId=()=> 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,char=>{const value=Math.floor(Math.random()*16);return (char==='x'?value:(value&3)|8).toString(16)});
const localDate=(value:Date)=>`${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`;
export function personalWeekStart(day:string){const d=new Date(day+'T12:00:00');d.setDate(d.getDate()-(d.getDay()+6)%7);return localDate(d)}
export default function LifeNavigationScreen(){const {user}=useAuth();return user?<PersonalWeek key={user.id} owner={user.id}/>:<Text>请登录后查看本人安排。</Text>}
function PersonalWeek({owner}:{owner:number}){
 const {c}=useTheme(),router=useRouter();
 const [workspace,setWorkspace]=useState<LifeWorkspace|null>(null),[title,setTitle]=useState(''),[criterion,setCriterion]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0);
 const [today,setToday]=useState(localDate(new Date()));const weekKey=personalWeekStart(today);
 const epoch=useRef(0),lock=useRef(false);
 useEffect(()=>subscribeAIConsentInvalidation(()=>{epoch.current++;setWorkspace(null);setTitle('');setCriterion('');setBusy(false);setMessage('登录状态已变化，请重新打开导航。')}),[]);
 useEffect(()=>{const sub=AppState.addEventListener('change',state=>{if(state==='active'){setToday(localDate(new Date()));setRefresh(v=>v+1)}else{epoch.current++;setWorkspace(null)}});return ()=>sub.remove()},[]);
 useFocusEffect(useCallback(()=>{const version=++epoch.current;setWorkspace(null);setToday(localDate(new Date()));fetchLifeWorkspace(owner).then(data=>{if(version===epoch.current)setWorkspace(data)}).catch(()=>{if(version===epoch.current)setMessage('个人安排暂不可用，请重新读取。')});return ()=>{epoch.current++}},[owner,refresh]));
 const week=workspace?.data?.weeks?.[weekKey],tasks=week?.tasks??[];
 const button=(label:string,press:()=>void)=><Pressable accessibilityRole="button" accessibilityLabel={label} disabled={busy} onPress={press} style={{padding:14,borderWidth:1,borderColor:c.separator,borderRadius:12}}><Text style={{color:c.brand}}>{label}</Text></Pressable>;
 async function save(data:LifeData){
  if(!workspace||lock.current)return;lock.current=true;setBusy(true);const version=epoch.current;
  try{const saved=await saveLifeWorkspace(owner,workspace.revision??0,data);if(version===epoch.current){setWorkspace(saved);setTitle('');setCriterion('');setMessage('已保存个人安排')}}
  catch(error){if(version===epoch.current)setMessage((error as {response?:{status:number}}).response?.status===409?'另一设备已更新，草稿已保留，请重新读取后核对。':'保存失败，草稿已保留。')}
  finally{lock.current=false;if(version===epoch.current)setBusy(false)}
 }
 function withTasks(next:LifeTask[]):LifeData{return {...workspace?.data,weeks:{...workspace?.data?.weeks,[weekKey]:{...week,tasks:next}}}}
 function add(){if(!workspace||!title.trim())return;void save(withTasks([...tasks,{id:taskId(),date:today,title:title.trim(),criterion,role:tasks.filter(t=>t.date===today&&t.role==='main').length?'other':'main',track_id:'main',slot:'flexible',status:'planned',estimated_minutes:null,actual_minutes:null,result:'',root_cause:'',improvement:''}]))}
 return <><Stack.Screen options={{title:'周导航',headerShown:true,headerBackTitle:'返回'}}/><ScrollView style={{backgroundColor:c.bgPrimary}} contentContainerStyle={{padding:22,gap:14}}>
  <Text style={{fontSize:24,fontWeight:'700',color:c.labelPrimary}}>周导航</Text><Text style={{color:c.labelSecondary}}>人生战略导航仪 · 本周 {weekKey}</Text>
  <Text style={{color:c.labelSecondary}}>这里记录个人安排。健康执行请在 Health 中确认；时段计时不代表任务已完成。</Text>
  {button('查看健康周导航',()=>router.push('/my-progress?navigation=week' as any))}
  {message&&<Text accessibilityRole="alert" style={{color:c.labelSecondary}}>{message}</Text>}
  {!workspace&&<ActivityIndicator/>}
  {workspace&&<>
   <Text style={{color:c.labelPrimary,fontWeight:'700'}}>今日 {today}</Text>
   {!tasks.filter(t=>t.date===today).length&&<Text style={{color:c.labelSecondary}}>还没有个人安排。</Text>}
   {tasks.filter(t=>t.date===today).map(task=><View key={task.id} style={{padding:16,borderRadius:12,backgroundColor:c.bgCard,gap:8}}><Text style={{color:c.labelPrimary}}>{task.role==='main'?'主任务 · ':''}{task.title}</Text><Text style={{color:c.labelSecondary}}>{task.criterion||'完成标准待填写'}</Text><Text style={{color:c.labelSecondary}}>{task.status==='done'?'个人任务已完成':task.status==='skipped'?'已跳过':'待处理'}</Text>{task.status!=='done'&&button('确认个人任务完成',()=>void save(withTasks(tasks.map(t=>t.id===task.id?{...t,status:'done'}:t))))}</View>)}
   <TextInput accessibilityLabel="个人任务标题" value={title} onChangeText={setTitle} maxLength={4000} placeholder="今天最重要的个人安排" style={{padding:14,color:c.labelPrimary,borderWidth:1,borderColor:c.separator,borderRadius:12}}/>
   <TextInput accessibilityLabel="完成标准" value={criterion} onChangeText={setCriterion} maxLength={4000} placeholder="如何知道这件事做完了" style={{padding:14,color:c.labelPrimary,borderWidth:1,borderColor:c.separator,borderRadius:12}}/>
   {button('加入今日安排',add)}
   <Text style={{color:c.labelPrimary,fontWeight:'700'}}>本周安排</Text>{tasks.filter(t=>t.date!==today).map(task=><Text key={task.id} style={{color:c.labelSecondary}}>{task.date} · {task.title}</Text>)}
   <Text style={{color:c.labelPrimary,fontWeight:'700'}}>周复盘</Text><Text style={{color:c.labelSecondary}}>{week?.review?.summary||'尚未填写。详细规划、季度更新与备份可在 Web 今日议程的周导航模式编辑。'}</Text>
   <Text style={{color:c.labelTertiary}}>已保存版本 {workspace.revision??0} · 未记录不等于未完成</Text>
  </>}
  {button('重新读取个人安排',()=>setRefresh(v=>v+1))}
 </ScrollView></>;
}
