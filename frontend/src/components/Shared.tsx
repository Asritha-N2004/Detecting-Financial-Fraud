import type {ReactNode} from 'react';
import {AlertTriangle,ArrowUpRight} from 'lucide-react';
import {Link} from 'react-router-dom';
export const human=(s:string)=>s.replaceAll('_',' ');
export const number=(n:number|null|undefined,d=1)=>n==null?'Unavailable':n.toLocaleString(undefined,{maximumFractionDigits:d});
export function Badge({value}:{value:string}){return <span className={`badge ${value.includes('high')||['failed','funding_shortfall'].includes(value)?'danger':value.includes('warning')||['moderate','partial','unavailable'].includes(value)?'warning':'neutral'}`}>{human(value)}</span>}
export function Panel({title,children,aside}:{title:string;children:ReactNode;aside?:ReactNode}){return <section className="panel"><div className="panel-title"><h2>{title}</h2>{aside}</div>{children}</section>}
export function ErrorBox({message}:{message:string}){return <div role="alert" className="error"><AlertTriangle size={18}/>{message}</div>}
export function Empty({title,description}:{title:string;description:string}){return <div className="empty"><h3>{title}</h3><p>{description}</p><Link to="/new" className="text-link">Create an assessment <ArrowUpRight size={16}/></Link></div>}
