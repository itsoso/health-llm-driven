import api from './api';
import type { AxiosRequestConfig } from 'axios';
import type { components } from '../types/api.generated';
import { aiConsentRevision } from './aiConsentState';
export type LifeWorkspace=components['schemas']['LifeWorkspace-Output'];
export type LifeData=components['schemas']['LifeData-Input'];
export type LifeTask=components['schemas']['Task'];
async function request<T>(owner:number,send:(config:AxiosRequestConfig)=>Promise<{data:T}>):Promise<T>{
 const revision=aiConsentRevision();
 const config={headers:{'X-Reva-AI-Subject':String(owner)},__revaConsentRevision:revision} as AxiosRequestConfig;
 const {data}=await send(config);
 if(revision!==aiConsentRevision())throw new Error('登录状态已变化，请重新打开导航。');
 return data;
}
export const fetchLifeWorkspace=(owner:number)=>request(owner,config=>api.get<LifeWorkspace>('/life-navigation/workspace',config));
export const saveLifeWorkspace=(owner:number,revision:number,data:LifeData)=>request(owner,config=>api.put<LifeWorkspace>('/life-navigation/workspace',{expected_revision:revision,data},config));
