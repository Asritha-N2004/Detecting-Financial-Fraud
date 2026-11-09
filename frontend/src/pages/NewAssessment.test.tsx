import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {describe,it,expect,vi} from 'vitest';
import NewAssessment from './NewAssessment';
import {api} from '../api';
describe('assessment data entry',()=>{
 it('validates manual JSON before calling the API',async()=>{
  const post=vi.spyOn(api,'post');
  render(<QueryClientProvider client={new QueryClient()}><NewAssessment created={()=>{}}/></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText('Array of statement records'),{target:{value:'not-json'}});
  fireEvent.submit(screen.getByRole('button',{name:/Run risk assessment/}).closest('form')!);
  await waitFor(()=>expect(screen.getByRole('alert')).toBeInTheDocument());
  expect(post).not.toHaveBeenCalled();post.mockRestore();
 });
});
