import { api } from './api/client';

import type { components } from '@/types/api.generated';
export type ExamQuestion = components['schemas']['ExamQuestion'];
export type ExamProgress = components['schemas']['ExamProgress'];
export type ExamPractice = components['schemas']['ExamPractice'];
export type ExamAttemptWrite = components['schemas']['ExamAttemptWrite'];
export type ExamAttempt = components['schemas']['ExamAttempt'];
export type ExamAttempts = components['schemas']['ExamHistory'];
const config = (owner:number, signal?:AbortSignal) => ({headers:{'X-Reva-AI-Subject':String(owner)},signal});
export async function getExamPractice(owner:number,day:string,signal?:AbortSignal):Promise<ExamPractice> {
 return (await api.get('/life-navigation/exam/practice',{...config(owner,signal),params:{day}})).data;
}
export async function getExamAttempts(owner:number,questionId:string,offset=0,signal?:AbortSignal):Promise<ExamAttempts> {
 return (await api.get('/life-navigation/exam/attempts',{...config(owner,signal),params:{question_id:questionId,offset,limit:50}})).data;
}
export async function submitExamAttempt(owner:number,body:ExamAttemptWrite):Promise<ExamAttempt> {
 return (await api.post('/life-navigation/exam/attempts',body,config(owner))).data;
}
