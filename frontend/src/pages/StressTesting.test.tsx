import {render,screen} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import {StressSummary} from './StressTesting';
import type {StressOutput} from './StressTesting';
describe('stress funding constraint',()=>{
 it('does not show a score for positive closing cash after an earlier funding gap',()=>{
  const projection={status:'funding_shortfall',aggregate:null,funding_gap:25,first_shortfall_date:'2026-06-29',balance_residual:null,statement:null,limitations:[],timeline:[],bridge:{opening_cash:100,closing_cash:8}};
  const result={currency:'USD',baseline_projection:{...projection,status:'completed',first_shortfall_date:null,funding_gap:0},adverse_projection:projection,score_change:null,portfolio_impact:{return:null,pnl:null,value_after_shock:null}} as unknown as StressOutput;
  render(<StressSummary result={result}/>);
  expect(screen.getByRole('alert')).toHaveTextContent('A positive year-end cash balance does not fund an earlier deficit');
  expect(screen.getByText(/Scores are withheld/)).toBeInTheDocument();
  expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(2);
 });
});
