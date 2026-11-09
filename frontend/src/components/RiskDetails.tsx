import type {Result} from '../types';
import {Panel,Badge,human,number} from './Shared';

export function RiskDetails({result}:{result:Result}){
 const market=result.outputs.market,liquidity=result.outputs.liquidity;
 const p=market?.analytics?.portfolio,m=liquidity?.analytics?.maturity;
 return <>{p&&<Panel title="Portfolio covariance & diversification" aside={<Badge value={p.status}/>}>
  {p.covariance?<><p className="subtle">Sample covariance of aligned daily simple returns · {p.observations} observations · no forward filling</p><div className="table-scroll"><table><caption>Daily covariance matrix (return squared)</caption><thead><tr><th>Constituent</th>{p.symbols.map(s=><th key={s}>{s}</th>)}</tr></thead><tbody>{p.covariance.map((row,i)=><tr key={p.symbols[i]}><th>{p.symbols[i]}</th>{row.map((v,j)=><td key={j}>{number(v,8)}</td>)}</tr>)}</tbody></table></div>
  <h3 style={{marginTop:20}}>Volatility risk contributions</h3><div className="table-scroll"><table><thead><tr><th>Constituent</th><th>Weight</th><th>Annual volatility contribution</th><th>Variance share</th></tr></thead><tbody>{p.risk_contributions?.map(c=><tr key={c.symbol}><td>{c.symbol}</td><td>{number(c.weight*100)}%</td><td>{c.annualized_volatility_contribution==null?'Unavailable':number(c.annualized_volatility_contribution*100,3)+' pp'}</td><td>{c.variance_share==null?'Unavailable':number(c.variance_share*100)+'%'}</td></tr>)}</tbody></table></div><p className="subtle">Contributions sum to portfolio volatility. Negative contributions indicate a historical covariance hedge, not a guaranteed loss offset.</p>
  <details><summary>Constituent correlation matrix</summary><div className="table-scroll"><table><thead><tr><th>Constituent</th>{p.symbols.map(s=><th key={s}>{s}</th>)}</tr></thead><tbody>{p.correlation?.map((row,i)=><tr key={p.symbols[i]}><th>{p.symbols[i]}</th>{row.map((v,j)=><td key={j}>{number(v,4)}</td>)}</tr>)}</tbody></table></div></details></>:<p>No covariance estimate is available for these inputs.</p>}
  {p.limitations.map((text,i)=><p className="subtle" key={i}>{text}</p>)}
 </Panel>}
 {m&&<Panel title="Debt maturity & funding gaps" aside={<Badge value={m.status}/>}>
  <p className="section-intro">As of {m.as_of||'unavailable'} · Opening cash and supplied dated flows; no assumed refinancing.</p>
  <div className="stats"><div className="stat"><span>Principal due within 365 days</span><strong>{number(liquidity.metrics.principal_due_365d?.value)}</strong></div><div className="stat"><span>Peak supplied-flow funding gap</span><strong>{number(liquidity.metrics.peak_scheduled_funding_gap?.value)}</strong></div><div className="stat"><span>Weighted maturity / years</span><strong>{number(liquidity.metrics.weighted_average_maturity_years?.value,2)}</strong></div><div className="stat"><span>First cash shortfall</span><strong style={{fontSize:18}}>{m.first_shortfall_date||'None observed'}</strong></div></div>
  {m.buckets&&<div className="table-scroll"><table><thead><tr><th>Days from as of</th><th>Principal</th><th>Interest</th><th>Operating inflow</th><th>Operating outflow</th><th>Net flow</th></tr></thead><tbody>{m.buckets.map(b=><tr key={b.bucket}><td>{human(b.bucket)}</td><td>{number(b.principal)}</td><td>{number(b.interest)}</td><td>{number(b.operating_inflow)}</td><td>{number(b.operating_outflow)}</td><td>{number(b.net_flow)}</td></tr>)}</tbody></table></div>}
  {m.limitations.map((text,i)=><p className="subtle" key={i}>{text}</p>)}<div className="info-note">Funding adequacy cannot be established from an incomplete debt or operating-flow profile. Amounts use the assessment currency.</div>
 </Panel>}</>
}
