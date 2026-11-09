import axios from 'axios';
import type {Assessment,Listing} from './types';
export const api=axios.create({baseURL:import.meta.env.VITE_API_BASE_URL||'/api/v1',timeout:30000});
api.interceptors.request.use(c=>{const token=sessionStorage.getItem('risk_token');if(token)c.headers.Authorization=`Bearer ${token}`;return c});
export function errorMessage(e:unknown):string {return axios.isAxiosError(e)?String(e.response?.data?.error?.message||e.message):e instanceof Error?e.message:'Request failed'}
export const listAssessments=(offset=0)=>api.get<Listing>('/assessments',{params:{offset,limit:20}}).then(r=>r.data);
export const getAssessment=(id:string)=>api.get<Assessment>(`/assessments/${id}`).then(r=>r.data);
