import {useState} from 'react';
import {Panel,ErrorBox} from './Shared';
import {errorMessage} from '../api';

export function EvidenceBundleImport({run,busy}:{run:(body:unknown)=>void;busy:boolean}){
 const [bundle,setBundle]=useState<unknown>(null),[error,setError]=useState(''),[name,setName]=useState('');
 return <Panel title="Import a complete evidence bundle"><p className="section-intro">JSON assessment bundles can include constituent holdings, per-source provenance, dated debt payments and operating flows. The API validates currency, weights, dates and accounting inputs.</p><label>Complete assessment JSON<input type="file" accept=".json" disabled={busy} onChange={async e=>{const file=e.target.files?.[0];setBundle(null);setError('');setName('');if(!file)return;try{if(file.size>2000000)throw new Error('Bundle exceeds 2 MB');const value:unknown=JSON.parse(await file.text());if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Evidence bundle must be a JSON object');setBundle(value);setName(file.name)}catch(ex){setError(errorMessage(ex))}}}/></label>{name&&<p>{name} staged for server validation.</p>}{error&&<ErrorBox message={error}/>}<button type="button" className="primary" disabled={!bundle||busy} onClick={()=>run(bundle)}>{busy?'Creating assessment…':'Import bundle and run'}</button></Panel>
}
