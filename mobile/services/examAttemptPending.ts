import * as SecureStore from 'expo-secure-store';
import type { ExamAttemptWrite } from './examPractice';
const operations=new Map<number,Promise<unknown>>();
function serialize<T>(owner:number,run:()=>Promise<T>):Promise<T>{
 const previous=operations.get(owner)??Promise.resolve();
 const next=previous.then(run,run);
 const settled=next.then(()=>undefined,()=>undefined);operations.set(owner,settled);
 void settled.then(()=>{if(operations.get(owner)===settled)operations.delete(owner);});
 return next;
}
const key=(owner:number)=>{
 if(!Number.isSafeInteger(owner)||owner<=0)throw new Error('无效的练习账号');
 return `exam_pending_v1_${owner}`;
};
function parse(raw:string):ExamAttemptWrite {
 const value:unknown=JSON.parse(raw);
 if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('待确认作答格式无效');
 const p=value as Record<string,unknown>;
 if(Object.keys(p).sort().join(',')!=='choice_index,elapsed_seconds,question_id,question_version,request_id'||typeof p.request_id!=='string'||!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(p.request_id)||typeof p.question_id!=='string'||!p.question_id||p.question_id.length>100||!Number.isInteger(p.question_version)||(p.question_version as number)<1||!Number.isInteger(p.choice_index)||(p.choice_index as number)<0||(p.choice_index as number)>9||!Number.isInteger(p.elapsed_seconds)||(p.elapsed_seconds as number)<0||(p.elapsed_seconds as number)>21600)throw new Error('待确认作答格式无效');
 return p as ExamAttemptWrite;
}
async function read(owner:number):Promise<ExamAttemptWrite|null>{const raw=await SecureStore.getItemAsync(key(owner));return raw?parse(raw):null;}
export const readPendingExamAttempt=(owner:number):Promise<ExamAttemptWrite|null>=>serialize(owner,()=>read(owner));
export const writePendingExamAttempt=(owner:number,body:ExamAttemptWrite):Promise<void>=>serialize(owner,async()=>{
 const previous=await read(owner);
 if(previous&&JSON.stringify(previous)!==JSON.stringify(body))throw new Error('请先确认上一条作答');
 await SecureStore.setItemAsync(key(owner),JSON.stringify(body));
});
export const clearPendingExamAttempt=(owner:number,requestId:string):Promise<void>=>serialize(owner,async()=>{
 const previous=await read(owner);
 if(previous&&previous.request_id!==requestId)throw new Error('待确认作答已改变');
 if(previous)await SecureStore.deleteItemAsync(key(owner));
});
