import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {EvidenceBundleImport} from './EvidenceBundleImport';
describe('complete evidence bundle import',()=>{
 it('stages constituent and debt inputs before an explicit run action',async()=>{
  const run=vi.fn();render(<EvidenceBundleImport run={run} busy={false}/>);
  const data={entity_name:'Synthetic company',portfolio_holdings:[],debt_schedule:{as_of:'2025-12-31'}};
  const file=new File([''], 'bundle.json',{type:'application/json'});
  Object.defineProperty(file,'text',{value:()=>Promise.resolve(JSON.stringify(data))});
  fireEvent.change(screen.getByLabelText('Complete assessment JSON'),{target:{files:[file]}});
  await waitFor(()=>expect(screen.getByRole('button')).toBeEnabled());
  expect(run).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button'));
  expect(run).toHaveBeenCalledWith(data);
 });
});
