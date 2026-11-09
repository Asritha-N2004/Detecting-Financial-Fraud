from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.providers.synthetic import synthetic
root=Path(__file__).resolve().parents[1]/'data'/'synthetic'
root.mkdir(parents=True,exist_ok=True)
for scenario in ['healthy','leveraged','volatile']:
    (root/f'{scenario}.json').write_text(synthetic(scenario).model_dump_json(indent=2))
print('Exported three clearly labeled synthetic evidence bundles')
