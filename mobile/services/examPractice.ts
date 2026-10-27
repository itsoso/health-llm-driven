import api from './api';
import type { AxiosRequestConfig } from 'axios';
import { aiConsentRevision } from './aiConsentState';

import type { components } from '../types/api.generated';
export type ExamQuestion = components['schemas']['ExamQuestion'];
export type ExamSubject = ExamQuestion['subject'];
export type ExamProgress = components['schemas']['ExamProgress'];
export type ExamPractice = components['schemas']['ExamPractice'];
export type ExamAttemptWrite = components['schemas']['ExamAttemptWrite'];
export type ExamAttempt = components['schemas']['ExamAttempt'];
export type ExamAttempts = components['schemas']['ExamHistory'];

async function request<T>(owner:number, send:(config:AxiosRequestConfig)=>Promise<{data:T}>):Promise<T> {
 const revision=aiConsentRevision();
 const config={headers:{'X-Reva-AI-Subject':String(owner)},__revaConsentRevision:revision} as AxiosRequestConfig;
 const {data}=await send(config);
 if(revision!==aiConsentRevision())throw new Error('登录状态已变化，请重新打开练习。');
 return data;
}
export const fetchExamPractice=(owner:number,day:string)=>request(owner,config=>api.get<ExamPractice>('/life-navigation/exam/practice',{...config,params:{day}}));
export const fetchExamAttempts=(owner:number,questionId:string,offset=0)=>request(owner,config=>api.get<ExamAttempts>('/life-navigation/exam/attempts',{...config,params:{question_id:questionId,offset,limit:50}}));
export const submitExamAttempt=(owner:number,body:ExamAttemptWrite)=>request(owner,config=>api.post<ExamAttempt>('/life-navigation/exam/attempts',body,config));
