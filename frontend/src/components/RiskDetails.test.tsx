import {render,screen} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import {RiskDetails} from './RiskDetails';
import type {Result,Agent} from '../types';
const agent:Agent={agent_id:'test',dimension:'market',status:'completed',score:20,confidence:'moderate',metrics:{},findings:[],limitations:[],summary:'Test',duration_seconds:0};
describe('portfolio and maturity transparency',()=>{
 it('renders covariance and distinct constituent contributions',()=>{
  const result={outputs:{market:{...agent,analytics:{portfolio:{status:'completed',symbols:['AAA','BBB'],covariance:[[.04,.01],[.01,.09]],risk_contributions:[{symbol:'AAA',weight:.5,annualized_volatility_contribution:.1,variance_share:.4}],limitations:[]}}},liquidity:agent}} as unknown as Result;
  render(<RiskDetails result={result}/>);
  expect(screen.getByText('Daily covariance matrix (return squared)')).toBeInTheDocument();
  expect(screen.getByText('Volatility risk contributions')).toBeInTheDocument();
  expect(screen.getByText('10 pp')).toBeInTheDocument();
 });
 it('discloses unavailable covariance and partial maturity coverage',()=>{
  const result={outputs:{market:{...agent,analytics:{portfolio:{status:'unavailable',symbols:[],limitations:['Calendars do not match']}}},liquidity:{...agent,analytics:{maturity:{status:'partial',limitations:['Operating receipts incomplete']}}}}} as unknown as Result;
  render(<RiskDetails result={result}/>);
  expect(screen.getByText('Calendars do not match')).toBeInTheDocument();
  expect(screen.getByText(/Funding adequacy cannot be established/)).toBeInTheDocument();
 });
});
