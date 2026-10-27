import api from '../api';
import { fetchExamPractice, fetchExamAttempts, submitExamAttempt } from '../examPractice';
import { invalidateAIConsent } from '../aiConsentState';
jest.mock('../api',()=>({__esModule:true,default:{get:jest.fn(),post:jest.fn()}}));
beforeEach(()=>jest.clearAllMocks());
it('binds reads and attempt writes to the initiating account without a workspace PUT',async()=>{
 (api.get as jest.Mock).mockResolvedValue({data:{}});(api.post as jest.Mock).mockResolvedValue({data:{id:'saved'}});
 await fetchExamPractice(7,'2026-10-28');await fetchExamAttempts(7,'e1',50);const body={request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12};await submitExamAttempt(7,body);
 expect(api.get).toHaveBeenCalledWith('/life-navigation/exam/practice',expect.objectContaining({headers:{'X-Reva-AI-Subject':'7'},params:{day:'2026-10-28'}}));expect(api.get).toHaveBeenCalledWith('/life-navigation/exam/attempts',expect.objectContaining({headers:{'X-Reva-AI-Subject':'7'},params:{question_id:'e1',offset:50,limit:50}}));expect(api.post).toHaveBeenCalledWith('/life-navigation/exam/attempts',body,expect.objectContaining({headers:{'X-Reva-AI-Subject':'7'}}));
});
it('rejects a stale response after account consent changes',async()=>{
 let finish!:(x:unknown)=>void;(api.get as jest.Mock).mockImplementation(()=>new Promise(r=>finish=r));const pending=fetchExamPractice(7,'2026-10-28');invalidateAIConsent();finish({data:{}});await expect(pending).rejects.toThrow('登录状态已变化');
});
