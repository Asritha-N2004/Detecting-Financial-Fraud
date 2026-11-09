"""Static research figure from observed controlled-ablation results."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parents[1]
source=root/'data'/'evaluation'/'results.json'
rows=json.loads(source.read_text())['results']
modes=['single','multi','critic','reflection']
labels=['Single specialist','Multi-agent','With critic','With reflection']
metric_names=['numerical_consistency','evidence_coverage','output_completeness']
titles=['Numerical consistency','Evidence reference coverage','Dimension completeness']
colors=['#82a99a','#548b78','#c49a51','#205c4b']
fig,axes=plt.subplots(1,3,figsize=(12,4.4),layout='constrained')
for ax,key,title in zip(axes,metric_names,titles):
    values=[np.mean([r['metrics'][key] for r in rows if r['mode']==mode and r['injected_faults']]) for mode in modes]
    bars=ax.bar(range(4),values,color=colors,width=.65)
    ax.set_xticks(range(4),labels,rotation=20,ha='right',fontsize=8)
    ax.set_ylim(0,1.12);ax.set_title(title,fontsize=11,loc='left',pad=14)
    ax.set_yticks([0,.25,.5,.75,1],['0%','25%','50%','75%','100%']);ax.tick_params(axis='y',labelsize=8)
    ax.bar_label(bars,labels=[f'{v:.1%}' for v in values],padding=5,fontsize=9)
    ax.spines[['top','right']].set_visible(False);ax.set_axisbelow(True);ax.grid(axis='y',alpha=.15)
fig.suptitle('Controlled injected-fault ablation | Mean across three synthetic scenarios',fontsize=13,fontweight='bold')
fig.supxlabel('Software consistency and reference checks only; no financial predictive accuracy claim.',fontsize=9)
fig.savefig(source.parent/'comparison.png',dpi=180)
fig.savefig(source.parent/'comparison.svg')
print('Saved data/evaluation/comparison.png and comparison.svg')
