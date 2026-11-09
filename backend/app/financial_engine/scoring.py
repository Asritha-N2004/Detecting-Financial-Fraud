from app.schemas.domain import AgentOutput


def category(score: float | None) -> str:
    return 'unavailable' if score is None else 'low' if score < 35 else 'moderate' if score < 65 else 'high'


def aggregate(outputs: dict[str, AgentOutput], weights: dict[str, float]) -> dict:
    contributions = {d: weights[d]*o.score for d,o in outputs.items() if o.score is not None and o.status == 'completed'}
    observed = sum(contributions.values())
    missing = [d for d,w in weights.items() if w > 0 and d not in contributions]
    remaining = sum(weights[d] for d in missing)
    return {'score': round(observed,4) if not missing else None, 'category': category(observed if not missing else None),
            'observed_contribution': observed, 'score_interval': [observed, observed+100*remaining],
            'coverage': 1-remaining, 'contributions': contributions, 'weights': weights, 'missing_dimensions': missing,
            'methodology': 'Fixed-weight bounded scores. Missing dimensions retain weight and contribute [0,100]; no redistribution. Heuristic scores are not calibrated probabilities.'}
