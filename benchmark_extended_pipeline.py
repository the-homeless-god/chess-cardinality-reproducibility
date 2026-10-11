"""Paired fresh full-pipeline benchmark on ten seeds, rotating mode order."""
import json,statistics,time
from pathlib import Path
from run_ga_experiment import prepare,run_mode,choice,GA,CONFIGS,SEEDS
from run_extended_comparisons import boot
ROOT=Path(__file__).parent;OUT=ROOT/'results_extended';MODES=['GA2','GA1+GA2','GA0+GA1+GA2','GA2_early_stop']
def main():
 rows=[]
 for seed in SEEDS:
  order=MODES[seed%4:]+MODES[:seed%4]
  for mode in order:
   start=time.perf_counter();data=prepare();prepared=time.perf_counter();tr=[r for r in data if r['split']=='train'];va=[r for r in data if r['split']=='val'];te=[r for r in data if r['split']=='test']
   if mode=='GA2_early_stop':
    ga=GA(seed,CONFIGS[1],tr,va);plateau=0;old=-1
    for _ in range(50):
     ga.generation();plateau=0 if ga.best_val>old else plateau+1;old=ga.best_val
     if ga.best_val>=.90 and plateau>=3:break
    weights=ga.best_weights;evals=ga.evaluations
   else:
    run=run_mode(mode,seed,tr,va);weights=run['weights'];evals=run['fitness_evaluations']
   fitted=time.perf_counter();picked=[choice(r,weights) for r in te];finish=time.perf_counter()
   rec={'seed':seed,'mode':mode,'prepare_seconds':prepared-start,'fit_seconds':fitted-prepared,'total_seconds':finish-start,'fitness_evaluations':evals,'test_accuracy':statistics.mean(r['scores'][j]==r['best'] for r,j in zip(te,picked))};rows.append(rec);(OUT/'pipeline_runs.json').write_text(json.dumps(rows,indent=2)+'\n');print(seed,mode,round(rec['total_seconds'],3),flush=True)
 modes={m:{k:statistics.mean(r[k] for r in rows if r['mode']==m) for k in ['prepare_seconds','fit_seconds','total_seconds','fitness_evaluations','test_accuracy']} for m in MODES}
 by={s:{r['mode']:r for r in rows if r['seed']==s} for s in SEEDS}
 paired={m:{key:boot([by[s][m][key]-by[s]['GA0+GA1+GA2'][key] for s in SEEDS]) for key in ['total_seconds','fit_seconds']} for m in MODES if m!='GA0+GA1+GA2'}
 (OUT/'pipeline_summary.json').write_text(json.dumps({'seeds':list(SEEDS),'modes':modes,'paired_saving_cascade':paired,'scope':'Read saved March roots and exact labels, construct all features, fit, choose 50 held-out moves; no network or engine. Mode order rotates.'},indent=2)+'\n')
if __name__=='__main__':main()
