import {cloneElement,type ReactElement} from 'react';
import {render,screen,fireEvent,waitFor,cleanup,act} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import App from '../App';
import Dashboard from '../pages/Dashboard';
import NewAssessment from '../pages/NewAssessment';
import Workspace from '../pages/Workspace';
import StressTesting from '../pages/StressTesting';
import {SensitivityExplorer} from '../components/SensitivityExplorer';
import type {Assessment,Result,SensitivityReport} from '../types';
import {installApiHarness,jsonBody,deferred} from './apiHarness';
import rawAssessment from './fixtures/assessment.json';
import rawStress from './fixtures/stress.json';
import rawShortfall from './fixtures/shortfall.json';
import rawCustom from './fixtures/custom-sensitivity.json';
import rawHistory from './fixtures/history-sensitivity.json';

// Keep real Recharts rendering; replace only browser-only container measurement.
vi.mock('recharts',async importOriginal=>{
 const actual=await importOriginal<typeof import('recharts')>();
 return {...actual,ResponsiveContainer:({children}:{children:ReactElement})=>cloneElement(children as ReactElement<{width:number;height:number}>,{width:600,height:250})};
});

const fixture=()=>JSON.parse(JSON.stringify(rawAssessment)) as Assessment;
const result=()=>fixture().result as Result;
let http:ReturnType<typeof installApiHarness>,client:QueryClient;
beforeEach(()=>{
 sessionStorage.clear();sessionStorage.setItem('risk_token','integration-token');
 http=installApiHarness();client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0,refetchOnWindowFocus:false},mutations:{retry:false}}});
});
afterEach(()=>{cleanup();client.clear();http.restore();vi.restoreAllMocks();sessionStorage.clear()});
function ui(element:ReactElement,path='/'){
 return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{element}</MemoryRouter></QueryClientProvider>);
}
const listing=(items:Assessment[],total=items.length)=>({items,total,offset:0,limit:20});
function savedAssessment(a=fixture()){
 http.when('GET',`/assessments/${a.id}`,()=>({data:a}));
 http.when('GET',`/assessments/${a.id}/job`,()=>({data:{status:'succeeded',attempts:1,max_attempts:3,next_node:'done',last_error:null,heartbeat_at:null,checkpoint_version:1}}));
 return a;
}
function fillManualForm(){
 fireEvent.change(screen.getByLabelText('Entity name'),{target:{value:'Submitted company'}});
 fireEvent.change(screen.getByLabelText('Provider'),{target:{value:'Annual report'}});
 fireEvent.change(screen.getByLabelText('Original source'),{target:{value:'Uploaded synthetic statement'}});
 fireEvent.change(screen.getByLabelText('Array of statement records'),{target:{value:JSON.stringify([{period:'2025-12-31',currency:'USD',current_assets:400,current_liabilities:100}])}});
}

describe('authentication and account boundaries through Axios',()=>{
 it('logs in and applies the returned bearer token to query requests',async()=>{
  sessionStorage.clear();http.when('POST','/auth/login',r=>{expect(jsonBody(r).email).toBe('analyst@example.com');return {data:{access_token:'new-token'}}});
  http.when('GET','/assessments',r=>{expect(r.headers.get('Authorization')).toBe('Bearer new-token');return {data:listing([fixture()])}});
  ui(<App/>);
  fireEvent.change(screen.getByLabelText('Email'),{target:{value:'analyst@example.com'}});
  fireEvent.change(screen.getByLabelText('Password'),{target:{value:'integration-password'}});
  fireEvent.click(screen.getByRole('button',{name:'Sign in'}));
  expect(await screen.findByRole('button',{name:'Aster Manufacturing'})).toBeInTheDocument();
  expect(sessionStorage.getItem('risk_token')).toBe('new-token');
 });
 it('renders a login rejection and never marks the session authenticated',async()=>{
  sessionStorage.clear();http.when('POST','/auth/login',()=>({status:401,data:{error:{message:'Invalid credentials'}}}));
  ui(<App/>);fireEvent.submit(screen.getByRole('button',{name:'Sign in'}).closest('form')!);
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
  expect(sessionStorage.getItem('risk_token')).toBeNull();
  expect(http.requests.some(r=>r.url==='/assessments')).toBe(false);
 });
 it('clears cached organization data and selection when switching accounts',async()=>{
  sessionStorage.setItem('risk_token','org-a');sessionStorage.setItem('risk_selected','private-a');
  const second=deferred<{data:ReturnType<typeof listing>}>();
  http.when('GET','/assessments',r=>r.headers.get('Authorization')==='Bearer org-a'?{data:listing([{...fixture(),entity_name:'Private organization A'}])}:second.promise);
  http.when('POST','/auth/login',()=>({data:{access_token:'org-b'}}));
  ui(<App/>);await screen.findByRole('button',{name:'Private organization A'});
  fireEvent.click(screen.getByTitle('Sign out'));
  expect(client.getQueryData(['assessments',0])).toBeUndefined();
  expect(sessionStorage.getItem('risk_selected')).toBeNull();
  fireEvent.submit(screen.getByRole('button',{name:'Sign in'}).closest('form')!);
  await waitFor(()=>expect(sessionStorage.getItem('risk_token')).toBe('org-b'));
  expect(screen.queryByRole('button',{name:'Private organization A'})).not.toBeInTheDocument();
  await act(async()=>second.resolve({data:listing([{...fixture(),id:'b',entity_name:'Organization B company'}])}));
  expect(await screen.findByRole('button',{name:'Organization B company'})).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Private organization A'})).not.toBeInTheDocument();
 });
});

describe('dashboard and creation API integration',()=>{
 it('fetches paginated rows and opens the chosen assessment',async()=>{
  const choose=vi.fn();http.when('GET','/assessments',r=>({data:listing([{...fixture(),id:Number(r.params.offset)===20?'b':'a',entity_name:Number(r.params.offset)===20?'Second page entity':'First page entity'}],21)}));
  ui(<Dashboard choose={choose}/>);await screen.findByRole('button',{name:'First page entity'});
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  fireEvent.click(await screen.findByRole('button',{name:'Second page entity'}));
  expect(choose).toHaveBeenCalledWith('b');expect(screen.getByRole('button',{name:'Next'})).toBeDisabled();
  expect(http.requests.some(r=>r.params?.offset===20&&r.params?.limit===20)).toBe(true);
 });
 it('shows server errors and does not fabricate assessment rows',async()=>{
  http.when('GET','/assessments',()=>({status:503,data:{error:{message:'Database temporarily unavailable'}}}));
  ui(<Dashboard choose={()=>{}}/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Database temporarily unavailable');
  expect(screen.queryByRole('button',{name:'Aster Manufacturing'})).not.toBeInTheDocument();
 });
 it('starts a demo and invalidates the assessment query after success',async()=>{
  const choose=vi.fn();http.when('GET','/assessments',()=>({data:listing([])}));
  http.when('POST','/demo/healthy',()=>({status:202,data:{id:'demo-id'}}));
  ui(<Dashboard choose={choose}/>);await screen.findByText('Your first assessment starts here');
  fireEvent.click(screen.getByRole('button',{name:/01.*Aster Manufacturing/}));
  await waitFor(()=>expect(choose).toHaveBeenCalledWith('demo-id'));
  await waitFor(()=>expect(http.requests.filter(r=>r.method==='get'&&r.url==='/assessments').length).toBeGreaterThan(1));
 });
 it('creates a manual assessment and navigates only after run acceptance',async()=>{
  const created=vi.fn(),start=deferred<{status:number;data:unknown}>();
  http.when('POST','/assessments',r=>{const body=jsonBody(r);expect(body.entity_name).toBe('Submitted company');expect(body.statements[0].current_assets).toBe(400);return {status:201,data:{id:'created-id'}}});
  http.when('POST','/assessments/created-id/run',()=>start.promise);
  ui(<NewAssessment created={created}/>);fillManualForm();
  fireEvent.submit(screen.getByRole('button',{name:'Run risk assessment'}).closest('form')!);
  await waitFor(()=>expect(http.requests.some(r=>r.url==='/assessments/created-id/run')).toBe(true));
  expect(created).not.toHaveBeenCalled();
  await act(async()=>start.resolve({status:202,data:{status:'running'}}));
  await waitFor(()=>expect(created).toHaveBeenCalledWith('created-id'));
 });
 it('surfaces run rejection without announcing successful creation',async()=>{
  const created=vi.fn();http.when('POST','/assessments',()=>({status:201,data:{id:'created-id'}}));
  http.when('POST','/assessments/created-id/run',()=>({status:503,data:{error:{message:'Unable to queue assessment'}}}));
  ui(<NewAssessment created={created}/>);fillManualForm();fireEvent.submit(screen.getByRole('button',{name:'Run risk assessment'}).closest('form')!);
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to queue assessment');expect(created).not.toHaveBeenCalled();
 });
 it('stages multipart data through the API and uses validated rows on submission',async()=>{
  const rows=[{period:'2025-12-31',currency:'USD',current_assets:600,current_liabilities:100}];
  http.when('POST','/data/financial-statements',r=>{expect(r.data).toBeInstanceOf(FormData);expect((r.data.get('file') as File).name).toBe('statements.csv');return {data:{rows}}});
  http.when('POST','/assessments',r=>{expect(jsonBody(r).statements).toEqual(rows);return {status:201,data:{id:'uploaded-id'}}});
  http.when('POST','/assessments/uploaded-id/run',()=>({status:202,data:{}}));
  const created=vi.fn();ui(<NewAssessment created={created}/>);fillManualForm();
  fireEvent.change(screen.getByLabelText('Array of statement records'),{target:{value:''}});
  fireEvent.change(screen.getByLabelText('Financial statements file'),{target:{files:[new File(['period,currency'], 'statements.csv',{type:'text/csv'})]}});
  await screen.findByText('statements.csv: 1 records validated');
  fireEvent.submit(screen.getByRole('button',{name:'Run risk assessment'}).closest('form')!);
  await waitFor(()=>expect(created).toHaveBeenCalledWith('uploaded-id'));
 });
 it('displays upload validation errors before any assessment is sent',async()=>{
  http.when('POST','/data/market-data',()=>({status:422,data:{error:{message:'Prices must be positive'}}}));
  ui(<NewAssessment created={()=>{}}/>);
  fireEvent.change(screen.getByLabelText('Market prices file'),{target:{files:[new File(['bad'], 'prices.csv')]}});
  expect(await screen.findByRole('alert')).toHaveTextContent('Prices must be positive');
  expect(http.requests.some(r=>r.url==='/assessments')).toBe(false);
 });
});

describe('assessment polling and error states',()=>{
 it('resumes request-bound saved work and refreshes completed results',async()=>{
  const a=fixture();let resumed=false;
  http.when('GET',`/assessments/${a.id}`,()=>({data:resumed?a:{...a,status:'running',result:null}}));
  http.when('GET',`/assessments/${a.id}/job`,()=>({data:{status:resumed?'succeeded':'queued',attempts:1,max_attempts:3,next_node:'critic',request_worker_enabled:true}}));
  http.when('POST',`/assessments/${a.id}/work`,()=>{resumed=true;return {status:202,data:{status:'accepted'}}});
  ui(<Workspace id={a.id} page="analysis"/>);
  fireEvent.click(await screen.findByRole('button',{name:'Resume saved work'}));
  expect(await screen.findByRole('heading',{name:'Quantitative indicators'})).toBeInTheDocument();
  expect(resumed).toBe(true);
  await waitFor(()=>expect(screen.queryByRole('button',{name:'Resume saved work'})).not.toBeInTheDocument());
 });
 it('polls a durable job into completed results through React Query',async()=>{
  const a=fixture();let reads=0;
  http.when('GET',`/assessments/${a.id}`,()=>({data:++reads===1?{...a,status:'running',result:null}:a}));
  http.when('GET',`/assessments/${a.id}/job`,()=>({data:{status:reads>1?'succeeded':'running',attempts:2,max_attempts:3,next_node:'critic',last_error:'WorkerShutdown'}}));
  ui(<Workspace id={a.id} page="analysis"/>);
  expect(await screen.findByRole('heading',{name:'Workflow in progress'})).toBeInTheDocument();
  expect(await screen.findByRole('heading',{name:'Quantitative indicators'},{timeout:4000})).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'Workflow in progress'})).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Recovered from a previous attempt');expect(reads).toBeGreaterThan(1);
 });
 it.each([401,404])('renders HTTP %s without exposing old assessment results',async status=>{
  http.when('GET','/assessments/missing',()=>({status,data:{error:{message:status===401?'Authentication required':'Assessment not found'}}}));
  ui(<Workspace id="missing" page="analysis"/>);
  expect(await screen.findByRole('alert')).toHaveTextContent(status===401?'Authentication required':'Assessment not found');
  expect(screen.queryByRole('heading',{name:'Quantitative indicators'})).not.toBeInTheDocument();
 });
 it('renders a failed workflow explicitly and does not display successful charts',async()=>{
  const a={...fixture(),status:'failed',result:undefined,error_message:'Recovery attempts exhausted'};savedAssessment(a);
  ui(<Workspace id={a.id} page="analysis"/>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Recovery attempts exhausted');
  expect(screen.queryByRole('heading',{name:'Quantitative indicators'})).not.toBeInTheDocument();
 });
 it('keeps an unavailable risk score distinct from zero after an agent failure',async()=>{
  const a=fixture(),r=a.result!;r.aggregate={...r.aggregate,score:null,category:'unavailable',coverage:.75,score_interval:[30,55],missing_dimensions:['market']};r.sensitivity=undefined;
  r.outputs.market={...r.outputs.market,status:'failed',score:null,confidence:'unavailable',summary:'Agent unavailable'};
  r.explanation.summary='Overall score withheld because market evidence is unavailable';savedAssessment(a);
  ui(<Workspace id={a.id} page="analysis"/>);
  expect(await screen.findByText('Bounded interval 30–55')).toBeInTheDocument();
  expect(screen.getByText('Overall score withheld because market evidence is unavailable')).toBeInTheDocument();
 });
 it('renders recorded reflection corrections and evidence-linked explanations',async()=>{
  const a=fixture(),r=a.result!;r.reflections=[{iteration_number:1,issues_detected:[],corrections_requested:['market'],corrections_completed:['market:score_mismatch'],unresolved_issues:[],score_before:r.aggregate,score_after:r.aggregate,verification_result:'verified'}];savedAssessment(a);
  const view=ui(<Workspace id={a.id} page="reflection"/>);
  expect(await screen.findByRole('heading',{name:'Reflection 1 / Targeted correction'})).toBeInTheDocument();
  expect(screen.getByText('Resolved: market:score_mismatch')).toBeInTheDocument();
  view.rerender(<QueryClientProvider client={client}><MemoryRouter><Workspace id={a.id} page="explanation"/></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole('heading',{name:'Executive summary'})).toBeInTheDocument();
  expect(screen.getAllByText(/statements:2/).length).toBeGreaterThan(0);
 });
 it('loads authorized audit events through the API',async()=>{
  const a=savedAssessment();http.when('GET',`/assessments/${a.id}/audit`,r=>{expect(r.headers.get('Authorization')).toBe('Bearer integration-token');return {data:[{id:'event',action:'sensitivity_analyzed',timestamp:'2026-11-09T00:00:00Z',metadata:{transfer_steps:[.05]}}]}});
  ui(<Workspace id={a.id} page="audit"/>);
  expect(await screen.findByText('sensitivity analyzed')).toBeInTheDocument();
 });
});

describe('sensitivity and stress API integration',()=>{
 it('validates explicit weights then displays a server diagnostic without changing the saved score',async()=>{
  const r=result();http.when('POST','/assessments/fixture-a/sensitivity',request=>{expect(jsonBody(request).weights).toEqual(rawCustom.baseline.weights);expect(jsonBody(request).transfer_steps).toEqual([.05]);return {data:rawCustom}});
  ui(<SensitivityExplorer id="fixture-a" aggregate={r.aggregate} saved={r.sensitivity}/>);
  fireEvent.change(screen.getByLabelText('credit weight (%)'),{target:{value:'20'}});
  expect(screen.getByRole('button',{name:'Explore weights'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('market weight (%)'),{target:{value:'30'}});
  fireEvent.click(screen.getByRole('button',{name:'Explore weights'}));
  await waitFor(()=>expect(http.requests.filter(r=>r.method==='post').length).toBe(1));
  await waitFor(()=>expect(screen.getByText(/Category changes \/ scenarios/)).toBeInTheDocument());
  expect(screen.getAllByText(r.aggregate.score!.toLocaleString(undefined,{maximumFractionDigits:1})).length).toBeGreaterThan(0);
  expect(http.requests.some(r=>r.url?.endsWith('/run'))).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Reset to saved weights'}));
  expect(screen.getByLabelText('credit weight (%)')).toHaveValue(25);
 });
 it('shows API validation failure without announcing updated diagnostics',async()=>{
  const r=result();http.when('POST','/assessments/fixture-a/sensitivity',()=>({status:422,data:{error:{message:'Unsupported diagnostic configuration'}}}));
  ui(<SensitivityExplorer id="fixture-a" aggregate={r.aggregate} saved={r.sensitivity}/>);
  fireEvent.click(screen.getByRole('button',{name:'Explore weights'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unsupported diagnostic configuration');
 });
 it('renders supplied score-history correlations with synthetic and constant-dimension disclosures',async()=>{
  const r=result();ui(<SensitivityExplorer id="fixture-a" aggregate={r.aggregate} saved={rawHistory as unknown as SensitivityReport}/>);
  expect(screen.getByText(/SYNTHETIC HISTORY/)).toBeInTheDocument();
  expect(screen.getByText('Constant score dimensions have undefined correlations')).toBeInTheDocument();
 });
 it('sends a selected scenario and displays the backend funding constraint',async()=>{
  http.when('POST','/assessments/fixture-a/stress-tests',r=>{expect(jsonBody(r)).toEqual({scenario:'combined_adverse'});return {data:rawShortfall}});
  ui(<StressTesting id="fixture-a"/>);
  fireEvent.change(screen.getByRole('combobox',{name:'Scenario'}),{target:{value:'combined_adverse'}});
  fireEvent.click(screen.getByRole('button',{name:'Run stress test'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('does not fund an earlier deficit');
  expect(screen.getByText(/Scores are withheld/)).toBeInTheDocument();
 });
 it('rejects malformed constituent overrides locally before sending a request',async()=>{
  ui(<StressTesting id="fixture-a"/>);fireEvent.click(screen.getByLabelText('Override preset assumptions'));
  fireEvent.change(screen.getByLabelText('Constituent shocks (JSON, decimal returns)'),{target:{value:'invalid-json'}});
  fireEvent.click(screen.getByRole('button',{name:'Run stress test'}));
  expect(await screen.findByRole('alert')).toBeInTheDocument();expect(http.requests).toHaveLength(0);
 });
 it('discards previous stress results when switching a cached assessment',async()=>{
  const a=savedAssessment(),b=savedAssessment({...fixture(),id:'fixture-b',entity_name:'Other company'});
  client.setQueryData(['assessment',a.id],a);client.setQueryData(['assessment',b.id],b);
  http.when('POST',`/assessments/${a.id}/stress-tests`,()=>({data:rawStress}));
  const view=ui(<Workspace id={a.id} page="stress"/>);
  fireEvent.click(await screen.findByRole('button',{name:'Run stress test'}));
  await screen.findByRole('heading',{name:'Hypothetical impact'});
  view.rerender(<QueryClientProvider client={client}><MemoryRouter><Workspace id={b.id} page="stress"/></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByText(/Other company \/ fixture-/)).toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:'Hypothetical impact'})).not.toBeInTheDocument();
 });
});
