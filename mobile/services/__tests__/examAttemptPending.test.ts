import * as SecureStore from 'expo-secure-store';
import { readPendingExamAttempt, writePendingExamAttempt, clearPendingExamAttempt } from '../examAttemptPending';
const body={request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12};
let store:Map<string,string>;
beforeEach(()=>{jest.clearAllMocks();store=new Map();(SecureStore.getItemAsync as jest.Mock).mockImplementation(async k=>store.get(k)??null);(SecureStore.setItemAsync as jest.Mock).mockImplementation(async(k,v)=>{store.set(k,v);});(SecureStore.deleteItemAsync as jest.Mock).mockImplementation(async k=>{store.delete(k);});});
it('persists only an owner-scoped unconfirmed request and clears only its matching receipt',async()=>{
 await writePendingExamAttempt(7,body);expect(await readPendingExamAttempt(7)).toEqual(body);expect(await readPendingExamAttempt(8)).toBeNull();await expect(writePendingExamAttempt(7,{...body,choice_index:1})).rejects.toThrow('先确认');await expect(clearPendingExamAttempt(7,'different')).rejects.toThrow('已改变');await clearPendingExamAttempt(7,body.request_id);expect(await readPendingExamAttempt(7)).toBeNull();
});
it('does not silently discard malformed or unreadable pending submissions',async()=>{
 store.set('exam_pending_v1_7','{"request_id":"broken"}');await expect(readPendingExamAttempt(7)).rejects.toThrow('格式无效');(SecureStore.getItemAsync as jest.Mock).mockRejectedValue(Error('locked'));await expect(readPendingExamAttempt(7)).rejects.toThrow('locked');
});

it('serializes simultaneous pending writes so a second request cannot overwrite the first',async()=>{
 const first=writePendingExamAttempt(7,body);const second=writePendingExamAttempt(7,{...body,request_id:'8d3fca50-1968-4c27-804c-ae508d33017d'});
 await first;await expect(second).rejects.toThrow('先确认');expect(await readPendingExamAttempt(7)).toEqual(body);
});

it('accepts the server duration boundary and rejects values beyond it on recovery',async()=>{
 store.set('exam_pending_v1_7',JSON.stringify({...body,elapsed_seconds:21600}));expect((await readPendingExamAttempt(7))?.elapsed_seconds).toBe(21600);
 store.set('exam_pending_v1_7',JSON.stringify({...body,elapsed_seconds:21601}));await expect(readPendingExamAttempt(7)).rejects.toThrow('格式无效');
});
