import {useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import {api,errorMessage} from '../api';
import type {Aggregate,SensitivityReport} from '../types';
import {Panel,Badge,ErrorBox,human,number} from './Shared';

export function SensitivityExplorer({id,aggregate,saved}:{id:string;aggregate:Aggregate;saved?:SensitivityReport}){
 const [weights,setWeights]=useState(()=>Object.fromEntries(Object.entries(aggregate.weights).map(([d,w])=>[d,String(w*100)])));
 const [step,setStep]=useState('5');
 const run=useMutation({mutationFn:()=>api.post<SensitivityReport>(`/assessments/${id}/sensitivity`,{weights:Object.fromEntries(Object.entries(weights).map(([d,w])=>[d,Number(w)/100])),transfer_steps:[Number(step)/100]}).then(r=>r.data)});
 const [useSaved,setUseSaved]=useState(true);
 const report=useSaved?saved:run.data;
 const values=Object.values(weights).map(Number),total=values.reduce((a,b)=>a+b,0);
 const valid=values.every(v=>Number.isFinite(v)&&v>=0&&v<=100)&&Math.abs(total-100)<1e-6;
 const reset=()=>{setWeights(Object.fromEntries(Object.entries(aggregate.weights).map(([d,w])=>[d,String(w*100)])));run.reset();setUseSaved(true)};
 return <Panel title="Overlapping risk & weight sensitivity" aside={<Badge value="diagnostic only"/>}>
  <p className="section-intro">Shared scoring inputs can influence several dimensions. Explore explicit weight transfers without changing the saved assessment.</p>
  <form onSubmit={e=>{e.preventDefault();if(valid){setUseSaved(false);run.mutate()}}}>
   <div className="form-grid">{Object.entries(weights).map(([d,w])=><label key={d}>{human(d)} weight (%)<input type="number" min={0} max={100} step="any" value={w} onChange={e=>setWeights({...weights,[d]:e.target.value})}/></label>)}<label>Weight transfer per scenario<select value={step} onChange={e=>setStep(e.target.value)}><option value="2">2 percentage points</option><option value="5">5 percentage points</option><option value="10">10 percentage points</option></select></label></div>
   {!valid&&<ErrorBox message="Exploratory weights must be between 0 and 100 and sum to 100%."/>}
   <button className="primary" disabled={!valid||run.isPending}>{run.isPending?'Analyzing sensitivity…':'Explore weights'}</button><button type="button" className="link-button" onClick={reset}>Reset to saved weights</button>
  </form>{run.error&&!useSaved&&<ErrorBox message={errorMessage(run.error)}/>}
  {report?<><div className="stats"><div className="stat"><span>Saved assessment / 100</span><strong>{number(aggregate.score)}</strong></div><div className="stat"><span>Exploratory baseline / 100</span><strong>{number(report.baseline.score)}</strong></div><div className="stat"><span>Sampled score envelope</span><strong style={{fontSize:22}}>{number(report.sampled_score_envelope[0])}–{number(report.sampled_score_envelope[1])}</strong></div><div className="stat"><span>Category changes / scenarios</span><strong>{report.category_changes} / {report.transfers.length}</strong></div></div>
   <p>Classification under sampled transfers: <strong>{report.classification_stable===null?'Uncertain — missing dimensions':report.classification_stable?'Unchanged':'Changes in some scenarios'}</strong></p>
   <h3 style={{marginTop:20}}>Shared input dependencies</h3><p className="subtle">This measures reused score-driving fields, not empirical correlation or a justified risk discount.</p>
   <div className="table-scroll"><table><thead><tr><th>Dimensions</th><th>Shared inputs</th><th>Input reuse</th></tr></thead><tbody>{report.structural.pairs.filter(p=>p.shared_inputs.length>0).map(p=><tr key={p.first+p.second}><td>{human(p.first)} / {human(p.second)}</td><td>{p.shared_inputs.map(human).join(', ')}</td><td>{p.shared_input_fraction==null?'Unavailable':number(p.shared_input_fraction*100,2)+'%'}</td></tr>)}</tbody></table></div>
   {report.structural.unavailable_dimensions.length>0&&<p className="amber">Dependency metadata unavailable for: {report.structural.unavailable_dimensions.join(', ')}. No overlap has been invented.</p>}
   <details><summary>Explicit weight-transfer scenarios ({report.transfers.length})</summary><div className="table-scroll"><table><thead><tr><th>Weight moved from / to</th><th>Actual transfer</th><th>Score</th><th>Score interval</th><th>Change</th><th>Category</th></tr></thead><tbody>{report.transfers.map((t,i)=><tr key={i}><td>{human(t.donor)} → {human(t.recipient)}</td><td>{number(t.actual_transfer*100)} pp</td><td>{number(t.aggregate.score)}</td><td>{t.aggregate.score_interval.map(v=>number(v)).join('–')}</td><td>{number(t.score_change)}</td><td><Badge value={t.aggregate.category}/></td></tr>)}</tbody></table></div></details>
   <h3 style={{marginTop:20}}>Empirical score correlation</h3>{report.empirical.correlation?<><p className="subtle">{report.empirical.complete_observations} complete observations · {report.empirical.dropped_incomplete} incomplete rows excluded · {report.empirical.provenance?.synthetic?'SYNTHETIC HISTORY':'SUPPLIED HISTORY'}</p><div className="table-scroll"><table><thead><tr><th>Dimension</th>{report.empirical.dimensions?.map(d=><th key={d}>{human(d)}</th>)}</tr></thead><tbody>{report.empirical.correlation.map((row,i)=><tr key={i}><th>{human(report.empirical.dimensions?.[i]||'')}</th>{row.map((v,j)=><td key={j}>{number(v,3)}</td>)}</tr>)}</tbody></table></div><p className="subtle">Source: {report.empirical.provenance?.source}. Historical aggregate-score standard deviation: {number(report.empirical.aggregate_score_standard_deviation,3)} points, not a probability.</p></>:<div className="info-note">{report.empirical.reason}</div>}
   {report.empirical.limitations?.map((text,i)=><p className="subtle" key={i}>{text}</p>)}
   <details><summary>Methodology & limitations</summary><p className="subtle">{report.structural.methodology}</p>{report.limitations.map((text,i)=><p className="subtle" key={i}>{text}</p>)}</details>
  </>:!run.isPending&&<div className="info-note">No saved sensitivity report is available for this older assessment. Explore weights to compute diagnostics from its saved outputs.</div>}
 </Panel>
}
