import api from '../api';
import { fetchLifeWorkspace,saveLifeWorkspace } from '../lifeNavigation';
jest.mock('../api',()=>({__esModule:true,default:{get:jest.fn(),put:jest.fn()}}));
it('binds private writes to the initiating owner and revision',async()=>{
 (api.put as jest.Mock).mockResolvedValue({data:{revision:2}});
 await saveLifeWorkspace(7,1,{weeks:{}});
 expect(api.put).toHaveBeenCalledWith('/life-navigation/workspace',{expected_revision:1,data:{weeks:{}}},expect.objectContaining({headers:{'X-Reva-AI-Subject':'7'}}));
});
it('discards a late previous-session planning response',async()=>{
 let done!:(value:unknown)=>void;
 (api.get as jest.Mock).mockImplementation(()=>new Promise(resolve=>{done=resolve}));
 const pending=fetchLifeWorkspace(1);
 require('../aiConsentState').invalidateAIConsent();done({data:{revision:1}});
 await expect(pending).rejects.toThrow('登录状态已变化');
});
