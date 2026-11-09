import {render,screen,fireEvent} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import {SpecialistInterpretation} from './Workspace';
import type {Agent} from '../types';

const agent:Agent={agent_id:'credit_analyst',dimension:'credit',status:'completed',score:40,confidence:'moderate',metrics:{},findings:[],limitations:[],summary:'Credit indicators',duration_seconds:.1};
describe('specialist interpretation disclosures',()=>{
 it('separates model interpretation from verified numeric results',()=>{
  render(<SpecialistInterpretation agent={{...agent,llm_interpretation:{status:'completed',provider:'test-provider',model:'test-model',validation:'Structural and reference checks only; semantic conclusions are unverified',error:null,prompt_sha256:'abcdef123456',usage:{tokens:25},analysis:{dimension:'credit',insights:[{kind:'monitoring',text:'Validate the leverage evidence.',finding_ids:['credit:debt_to_equity'],metric_refs:['debt_to_equity'],evidence_refs:['statements:2']}],limitations:['Historical evidence only']}}}}/>);
  fireEvent.click(screen.getByText(/LLM specialist interpretation/));
  expect(screen.getByText(/semantic conclusions are unverified/)).toBeInTheDocument();
  expect(screen.getByText('Validate the leverage evidence.')).toBeInTheDocument();
  expect(screen.getByText(/Evidence: statements:2/)).toBeInTheDocument();
 });
 it('shows failed interpretation without hiding deterministic availability',()=>{
  render(<SpecialistInterpretation agent={{...agent,llm_interpretation:{status:'failed',provider:'test',model:'test',validation:'Unverified',error:'TimeoutError',prompt_sha256:null,usage:{tokens:null},analysis:null}}}/>);
  expect(screen.getByText(/Deterministic metrics and findings remain available/)).toBeInTheDocument();
 });
});
