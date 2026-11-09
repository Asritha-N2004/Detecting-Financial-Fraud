"""Export an explicitly illustrative score-history dependency fixture."""
from pathlib import Path
from datetime import date,timedelta
import sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
from app.providers.synthetic import synthetic
from app.schemas.domain import AssessmentInput

data=synthetic();raw=data.model_dump(mode='json')
provenance={**raw['provenance'],'source':'Synthetic score-level dependency illustration; these historical scores are assumed, not measured company scores'}
raw['risk_score_history']={'entity_name':data.entity_name,'model_version':'rules-2.0','holding_days':1,'confidence':.95,
    'provenance':provenance,'observations':[{'date':str(date(2024,1,1)+timedelta(days=i)),
        'scores':{'credit':20+i%15,'financial':15+2*(i%15),'liquidity':60-i%15,'market':30+2*(i%7),'operational':20}} for i in range(60)]}
output=root/'data'/'synthetic'/'sensitivity_history.json'
output.write_text(AssessmentInput.model_validate(raw).model_dump_json(indent=2))
print('Exported explicitly synthetic score-history illustration to data/synthetic/sensitivity_history.json')
