import { beforeEach, expect, it, vi } from 'vitest';
import { api } from './api/client';
import { getExamPractice, getExamAttempts, submitExamAttempt } from './examPractice';
vi.mock('./api/client',()=>({api:{get:vi.fn(),post:vi.fn()}}));
beforeEach(()=>vi.clearAllMocks());
it('scopes every read and write to the authenticated owner contract',async()=>{
 vi.mocked(api.get).mockResolvedValue({data:{questions:[]}});vi.mocked(api.post).mockResolvedValue({data:{id:'saved'}});
 const signal=new AbortController().signal;
 await getExamPractice(7,'2026-10-28',signal);await getExamAttempts(7,'m01',50,signal);
 const body={request_id:'same-id',question_id:'m01',question_version:1,choice_index:4,elapsed_seconds:30};
 expect(await submitExamAttempt(7,body)).toEqual({id:'saved'});
 expect(api.get).toHaveBeenNthCalledWith(1,'/life-navigation/exam/practice',{headers:{'X-Reva-AI-Subject':'7'},signal,params:{day:'2026-10-28'}});
 expect(api.get).toHaveBeenNthCalledWith(2,'/life-navigation/exam/attempts',{headers:{'X-Reva-AI-Subject':'7'},signal,params:{question_id:'m01',offset:50,limit:50}});
 expect(api.post).toHaveBeenCalledWith('/life-navigation/exam/attempts',body,{headers:{'X-Reva-AI-Subject':'7'},signal:undefined});
});
it('propagates request failure without synthesizing saved progress',async()=>{vi.mocked(api.post).mockRejectedValue(Error('offline'));await expect(submitExamAttempt(7,{request_id:'same-id',question_id:'m01',question_version:1,choice_index:0,elapsed_seconds:3})).rejects.toThrow('offline');});
