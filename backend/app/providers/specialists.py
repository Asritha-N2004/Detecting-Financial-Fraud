"""OpenAI-compatible specialist provider. No client is opened in offline mode."""
import json
from app.core.config import settings
from app.schemas.domain import SpecialistAnalysis, StrictModel
from pydantic import Field


class MetricLookup(StrictModel):
    metric: str = Field(min_length=1,max_length=100)


class SpecialistProviderError(ValueError):
    def __init__(self, code: str, usage: dict):
        super().__init__(code)
        self.code=code
        self.usage=usage


class OpenAICompatibleSpecialist:
    def __init__(self, client=None):
        self.client=client

    async def analyze(self, dimension: str, packet: dict, prompt: str):
        from openai import AsyncOpenAI
        cfg=settings()
        usage={'provider':'openai-compatible','model':cfg.model_for_specialist(dimension),'tokens':0,'input_tokens':0,'output_tokens':0,'cost_usd':None,'requests':0,'tool_calls':[]}
        if self.client is None and not cfg.openai_api_key:
            raise SpecialistProviderError('Missing provider credential',usage)
        client=self.client or AsyncOpenAI(api_key=cfg.openai_api_key,base_url=cfg.openai_base_url,timeout=cfg.agent_timeout_seconds,max_retries=0)
        metrics=packet['metrics']
        # This request exposes only these keys, never IDs from other assessments.
        tool={'type':'function','function':{'name':'get_metric','description':'Read one server-computed metric from this specialist evidence packet.',
            'strict':True,'parameters':{'type':'object','properties':{'metric':{'type':'string','enum':list(metrics)}},'required':['metric'],'additionalProperties':False}}}
        schema=SpecialistAnalysis.model_json_schema()
        messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(packet,allow_nan=False)}]
        try:
            for round_index in range(cfg.llm_max_tool_rounds+1):
                response=await client.chat.completions.create(model=usage['model'],messages=messages,
                    response_format={'type':'json_schema','json_schema':{'name':'specialist_analysis','strict':True,'schema':schema}},
                    max_completion_tokens=cfg.llm_max_completion_tokens,
                    **({'tools':[tool],'tool_choice':'auto' if round_index<cfg.llm_max_tool_rounds else 'none','parallel_tool_calls':False} if metrics else {}))
                usage['requests']+=1
                if response.usage:
                    for dest,src in [('tokens','total_tokens'),('input_tokens','prompt_tokens'),('output_tokens','completion_tokens')]:
                        if usage[dest] is not None: usage[dest]+=getattr(response.usage,src)
                else:
                    usage.update(tokens=None,input_tokens=None,output_tokens=None)
                message=response.choices[0].message
                if getattr(message,'refusal',None):
                    raise SpecialistProviderError('Model refusal',usage)
                calls=message.tool_calls or []
                if calls:
                    if round_index>=cfg.llm_max_tool_rounds or len(calls)>4:
                        raise SpecialistProviderError('Tool budget exceeded',usage)
                    messages.append(message.model_dump(exclude_none=True))
                    for call in calls:
                        if call.type!='function' or call.function.name!='get_metric':
                            raise SpecialistProviderError('Unauthorized tool',usage)
                        args=MetricLookup.model_validate_json(call.function.arguments)
                        if args.metric not in metrics:
                            raise SpecialistProviderError('Unauthorized metric',usage)
                        usage['tool_calls'].append({'tool':'get_metric','metric':args.metric})
                        messages.append({'role':'tool','tool_call_id':call.id,'content':json.dumps(metrics[args.metric],allow_nan=False)})
                    continue
                if response.choices[0].finish_reason!='stop':
                    raise SpecialistProviderError('Incomplete response',usage)
                return SpecialistAnalysis.model_validate_json(message.content),usage
            raise SpecialistProviderError('Tool budget exhausted',usage)
        except SpecialistProviderError:
            raise
        except Exception as exc:
            raise SpecialistProviderError(type(exc).__name__,usage) from None
        finally:
            if self.client is None:
                await client.close()
