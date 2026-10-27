import type { LifeData, LifeTask } from '@/services/lifeNavigation';
import { blankTask, blankWeek, mondayOf } from './model';
import { paperAssignment } from './examPapers';
export const examDate = '2026-12-19';
export type Subject = '英语' | '数学' | '逻辑';
export interface StudyQuestion { id: string; subject: Subject; topic: string; prompt: string; options: string[]; answer: number; explanation: string }
export const questions: StudyQuestion[] = [
 {id:'e01',subject:'英语',topic:'词义与搭配',prompt:'The company decided to postpone the launch until the safety review was complete. “postpone” means:',options:['cancel permanently','delay until later','announce publicly','speed up'],answer:1,explanation:'postpone = 延后，不是永久取消。until 引导的条件提示：等待安全审查完成后再发布。'},
 {id:'e02',subject:'英语',topic:'逻辑关系',prompt:'Although remote work reduced commuting time, it did not necessarily improve productivity. Which statement is supported?',options:['Remote work always lowers productivity.','Commuting time and productivity are the same.','Less commuting does not guarantee higher productivity.','All workers prefer working remotely.'],answer:2,explanation:'although 表示让步；not necessarily 是“不一定”。原句未声称生产率一定下降。注意 always / all。'},
 {id:'e03',subject:'英语',topic:'主旨',prompt:'A store introduced self-checkout to cut waiting time. But many customers needed assistance. The manager added staff to guide users rather than removing the machines. The passage mainly describes:',options:['A complete failure of technology.','An adjustment to how new technology is used.','Why staff should be replaced.','A fall in demand for shopping.'],answer:1,explanation:'重点在问题出现后的调整。保留机器并增加引导，不能概括为技术彻底失败。'},
 {id:'e04',subject:'英语',topic:'因果与相关',prompt:'A survey found that employees who exercised regularly reported less stress. The researchers warned that the survey could not establish causation. What can we conclude?',options:['Exercise certainly caused lower stress.','Lower stress prevented exercise.','Exercise and reported stress were associated.','The survey proved exercise useless.'],answer:2,explanation:'associated 表示关联。调查不能排除其他变量或反向因果，不能选“确定导致”。'},
 {id:'e05',subject:'英语',topic:'指代',prompt:'Small firms often lack the funds to train employees. This can limit their ability to adopt new tools. “This” refers to:',options:['The lack of funds for training.','The size of the tools.','Employees adopting tools.','The existence of large firms.'],answer:0,explanation:'This 承接上一句的培训资金不足。将候选含义代回原句检验。'},
 {id:'e06',subject:'英语',topic:'态度',prompt:'The proposal is promising, but its costs and long-term effects remain uncertain. The author’s attitude is:',options:['Unconditionally supportive.','Entirely dismissive.','Cautiously positive.','Indifferent.'],answer:2,explanation:'promising 是正面评价，but 后是不确定性，因此是谨慎乐观。'},
 {id:'e07',subject:'英语',topic:'细节',prompt:'The library is open every weekday except Wednesday, when it closes for maintenance. On which day is it closed?',options:['Monday','Tuesday','Wednesday','Friday'],answer:2,explanation:'except 表示排除，条件定位时不要忽略限定词。'},
 {id:'e08',subject:'英语',topic:'条件',prompt:'The new policy may help small businesses, provided that the application process is simplified. The benefit depends on:',options:['Reducing the number of businesses.','Making applications easier.','Removing all regulations.','Raising application fees.'],answer:1,explanation:'provided that = 条件是。其余选项均超出原文。'},
 {id:'m01',subject:'数学',topic:'百分比',prompt:'商品先涨价 20%，再降价 20%，最终价格与原价相比如何？',options:['不变','降低 4%','提高 4%','降低 20%'],answer:1,explanation:'设原价100，100×1.2×0.8=96。两次百分比的基数不同。'},
 {id:'m02',subject:'数学',topic:'加权平均',prompt:'甲组10人平均分80，乙组20人平均分65，总平均分是多少？',options:['70','72.5','75','77.5'],answer:0,explanation:'(10×80+20×65)÷30=70，不能直接平均两组平均分。'},
 {id:'m03',subject:'数学',topic:'条件充分性',prompt:'判断 x 是否大于0。（1）x²=4；（2）x+1=3。以下哪项正确？',options:['仅（1）充分','仅（2）充分','各自都充分','合起来也不充分'],answer:1,explanation:'（1）x=±2，不能确定；（2）x=2，可以确定。'},
 {id:'m04',subject:'数学',topic:'排列组合',prompt:'从5人中选2人组成小组，不区分职位，有多少种选法？',options:['10','20','25','5'],answer:0,explanation:'不区分顺序：C(5,2)=5×4÷2=10。区分正副职位才是20。'},
 {id:'m05',subject:'数学',topic:'概率',prompt:'同时掷两枚均匀硬币，恰好一个正面的概率为？',options:['1/4','1/2','3/4','1'],answer:1,explanation:'四个等可能结果中正反、反正满足条件，概率2/4。'},
 {id:'m06',subject:'数学',topic:'方程应用',prompt:'甲完成工作需6天，乙需3天，两人合作需几天？',options:['1','2','3','4.5'],answer:1,explanation:'效率相加1/6+1/3=1/2，完成一份工作需2天。'},
 {id:'l01',subject:'逻辑',topic:'必要条件',prompt:'只有通过安全审查，产品才能发布。产品已经发布，可以推出？',options:['产品一定畅销','产品通过了安全审查','通过审查的产品都已发布','没有产品未通过审查'],answer:1,explanation:'只有P才Q，表示Q→P。发布推出通过审查，反之不成立。'},
 {id:'l02',subject:'逻辑',topic:'否定后件',prompt:'如果下雨，比赛就取消。比赛没有取消。可以推出？',options:['没有下雨','下雨了','比赛一定在室内','无法判断是否下雨'],answer:0,explanation:'P→Q，非Q→非P。否定后件可以否定前件。'},
 {id:'l03',subject:'逻辑',topic:'削弱',prompt:'店铺换招牌后销售额上涨，店主认为招牌导致增长。哪项最能削弱？',options:['招牌颜色鲜艳','店主喜欢招牌','同期竞争店停业，客流转入','招牌变大'],answer:2,explanation:'竞争店停业提供另一种合理原因，削弱原来的因果归因。'},
 {id:'l04',subject:'逻辑',topic:'集合',prompt:'所有项目经理都参加培训。有些受训者懂法语。能否推出有项目经理懂法语？',options:['一定能','一定没有','不能确定','所有经理都懂'],answer:2,explanation:'懂法语者可能在项目经理集合之外，也可能有交集，不能确定。'},
 {id:'l05',subject:'逻辑',topic:'加强',prompt:'研究者认为提醒短信能减少爽约。哪项最支持？',options:['短信便宜','随机分组后收到短信组爽约率低于未收到组','多数人有手机','医院喜欢短信'],answer:1,explanation:'随机对照更好控制其他因素，直接提供效果证据；成本不是效果。'},
 {id:'l06',subject:'逻辑',topic:'命题否定',prompt:'“所有参加者都交了作业”的否定是？',options:['所有人都没交','有参加者没交','有参加者交了','只有一人交了'],answer:1,explanation:'全称肯定的否定是特称否定：至少一人未交。'},
];
export function daysUntil(day:string) { return Math.round((Date.parse(examDate+'T00:00:00Z')-Date.parse(day+'T00:00:00Z'))/86400000); }
export function phaseFor(day:string) { const n=daysUntil(day);return n<0?'初试后：等待成绩与复试通知':n===0?'考试日：以准考证为准':n<=5?'收尾：错题回看与作息':n<=19?'冲刺：限时训练':n<=40?'强化：专项与真题':'起步：摸底与基础'; }
export function comprehensiveSubject(day:string):Subject|'写作' {
 const offset=Math.floor(Date.parse(day+'T00:00:00Z')/86400000);
 return (['数学','逻辑','写作'] as const)[((offset%3)+3)%3];
}
export function dailyStudy(day:string) {
 if(day>=examDate)return [];
 const assignment=paperAssignment(day);
 if(assignment) {
  const label=`${assignment.year}年真题 · ${assignment.review?'复测':'首轮分段'}`;
  return [
   {key:'paper-english',title:'英语（二）',minutes:45,detail:`${label}：${assignment.english}。限时作答25分钟，核对证据与生词20分钟。`},
   {key:'paper-comprehensive',title:'管综专项',minutes:40,detail:`${label}：${assignment.comprehensive}。先独立作答，再标记不会、误读、计算或超时。`},
   {key:'paper-writing',title:'写作训练',minutes:20,detail:`${assignment.year}年${assignment.writing}。这是分段训练，整篇写作另行安排。`},
   {key:'paper-review',title:'错题复盘',minutes:15,detail:'闭卷复做昨日错题，记录年份、科目、题号、实际用时、错因及下一次复测日期。无错题时回忆今天的解题依据。'}
  ];
 }
 const subject=comprehensiveSubject(day);
 return [{key:'english',title:'英语（二）',minutes:30,detail:'5分钟回忆词汇；20分钟限时阅读一篇并作答；5分钟回原文标注证据。四级基础起步，先测准确率。'},
 {key:'comprehensive',title:`管综 · ${subject}`,minutes:20,detail:subject==='写作'?'写一份论证有效性分析提纲：结论、前提和至少3个漏洞。之后单独安排整篇写作。':`限时练习${subject}，逐题说明依据；超过3分钟先标记，训练取舍。`},
 {key:'review',title:'错题复盘',minutes:10,detail:'闭卷重做错题；记录知识不会、条件读错、计算失误或时间不足，以及下一次如何避免。'}];
}
export function studyId(day:string,key:string):string {
 // Persisted identifiers: append keys only; never reorder or reuse a code.
 const index=['english','comprehensive','review','e01','e02','e03','e04','e05','e06','e07','e08','m01','m02','m03','m04','m05','m06','l01','l02','l03','l04','l05','l06','writing','paper-english','paper-comprehensive','paper-writing','paper-review'].indexOf(key);
 if(index<0||!/^\d{4}-\d{2}-\d{2}$/.test(day))throw Error('备考记录标识无效');
 return `e6ba2027-${day.slice(0,4)}-4${day.slice(5,7)}${day.slice(8,9)}-8${day.slice(9)}00-${(index+1).toString(16).padStart(12,'0')}`;
}
export function studyTask(data:LifeData,day:string,key:string):LifeTask|undefined {return data.weeks[mondayOf(day)]?.tasks.find(t=>t.id===studyId(day,key));}
function room(data:LifeData,day:string,count:number){const key=mondayOf(day);if(!data.weeks[key]&&Object.keys(data.weeks).length>=200)throw Error('工作区达到200周上限，请先整理。');if((data.weeks[key]?.tasks.length??0)+count>100)throw Error('每周最多100项任务，请先整理。');data.weeks[key]??=blankWeek();return data.weeks[key];}
export function addStudyDay(data:LifeData,day:string){const missing=dailyStudy(day).filter(t=>!studyTask(data,day,t.key));if(!missing.length)return;const w=room(data,day,missing.length);missing.forEach(t=>w.tasks.push({...blankTask(day,'other'),id:studyId(day,t.key),title:`备考｜${t.title}`,criterion:t.detail,estimated_minutes:t.minutes}));}
export function recordAnswer(data:LifeData,day:string,q:StudyQuestion,choice:number){
 if(!Number.isInteger(choice)||choice<0||choice>=q.options.length)throw Error('请选择有效答案');
 const old=studyTask(data,day,q.id);const w=room(data,day,old?0:1);const result=`作答：${String.fromCharCode(65+choice)}；正确答案：${String.fromCharCode(65+q.answer)}。\n${q.explanation}`;
 if(old){old.status=choice===q.answer?'done':'doing';old.improvement=result;}
 else w.tasks.push({...blankTask(day,'other'),id:studyId(day,q.id),title:`备考练习｜${q.subject} · ${q.topic}`,criterion:q.prompt,status:choice===q.answer?'done':'doing',result,estimated_minutes:0});
}
export function questionHistory(data:LifeData,q:StudyQuestion,day?:string){return Object.values(data.weeks).flatMap(w=>w.tasks).filter(t=>(!day||t.date<=day)&&t.id===studyId(t.date,q.id)).sort((a,b)=>a.date.localeCompare(b.date));}
export function wrongQuestions(data:LifeData,day?:string){return questions.filter(q=>questionHistory(data,q,day).at(-1)?.status==='doing');}

export type PracticeMode = 'next' | 'wrong' | 'all';
export const practiceModes: {key:PracticeMode;label:string}[] = [
 {key:'next',label:'按进度练习'}, {key:'wrong',label:'待复练'}, {key:'all',label:'全部题库'},
];
export function practiceQuestions(data:LifeData,day:string,subject:Subject,mode:PracticeMode='next'):StudyQuestion[] {
 const pool=questions.filter(q=>q.subject===subject);
 if(mode==='all')return pool;
 const history=pool.map(question=>({question,last:questionHistory(data,question,day).at(-1)}));
 if(mode==='wrong')return history.filter(({last})=>last?.status==='doing').map(({question})=>question);
 const review=history.filter(({last})=>last?.status==='doing'&&last.date<day);
 const unseen=history.filter(({last})=>!last||!['doing','done'].includes(last.status));
 return [...review,...unseen].map(({question})=>question);
}
