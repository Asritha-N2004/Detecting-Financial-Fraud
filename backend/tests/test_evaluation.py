import asyncio
from app.evaluation import experiment


def test_controlled_ablation_measures_real_corrections():
    raw=asyncio.run(experiment('healthy','multi',True))
    fixed=asyncio.run(experiment('healthy','reflection',True))
    assert fixed['metrics']['numerical_consistency']>raw['metrics']['numerical_consistency']
    assert fixed['metrics']['unsupported_claim_rate']==0
    assert fixed['metrics']['issue_resolution_rate']==1
    assert fixed['metrics']['contradiction_detection']==1
    assert fixed['iterations']==1
