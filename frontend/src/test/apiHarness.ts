import {AxiosError,AxiosHeaders,type AxiosResponse,type InternalAxiosRequestConfig} from 'axios';
import {api} from '../api';

type Reply={status?:number;data:unknown};
type Route={method:string;path:string|RegExp;handler:(request:InternalAxiosRequestConfig)=>Reply|Promise<Reply>};

/** Test HTTP boundary: real Axios transforms/interceptors and real Query hooks run. */
export function installApiHarness(){
 const original=api.defaults.adapter,routes:Route[]=[],requests:InternalAxiosRequestConfig[]=[];
 api.defaults.adapter=async config=>{
  requests.push(config);
  const route=routes.find(r=>r.method===config.method?.toUpperCase()&&(typeof r.path==='string'?r.path===config.url:r.path.test(config.url||'')));
  const reply=route?await route.handler(config):{status:404,data:{error:{message:'Unexpected test request: '+config.url}}};
  const response:AxiosResponse={data:reply.data,status:reply.status??200,statusText:'Test response',headers:new AxiosHeaders(),config};
  if(response.status>=400)throw new AxiosError('HTTP '+response.status,'ERR_BAD_RESPONSE',config,undefined,response);
  return response;
 };
 return {requests,when(method:string,path:string|RegExp,handler:Route['handler']){routes.unshift({method:method.toUpperCase(),path,handler})},restore(){api.defaults.adapter=original}};
}

export function jsonBody(request:InternalAxiosRequestConfig){return typeof request.data==='string'?JSON.parse(request.data):request.data}

export function deferred<T>(){
 let resolve!:(value:T)=>void;const promise=new Promise<T>(r=>{resolve=r});
 return {promise,resolve};
}
