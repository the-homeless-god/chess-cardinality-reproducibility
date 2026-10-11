"""Compute additional numerical summaries from saved trials."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).parent;OUT=ROOT/'results_search_integration_v1'
NAMES={'baseline':'Базовый поиск','A':'Только А','B':'Только Б','ABC':'Фиксированный АБВ','observed':'Смена по эффекту','inferred':'Смена по рангу','GA2':'Веса GA2','cascade':'Веса каскада'}
def main():
 s=json.loads((OUT/'summary.json').read_text());gs=json.loads((OUT/'games_summary.json').read_text());ds=json.loads((OUT/'depth_summary.json').read_text());roots=json.loads((ROOT/'data/search_integration_v1/positions.json').read_text());rows=json.loads((OUT/'scored_trials.json').read_text());labels={r['position_id']:r['response'] for r in map(json.loads,(ROOT/'results_scenarios_2025_04/responses.jsonl').read_text().splitlines())}
 cat={'win':2,'cursed-win':1,'draw':1,'blessed-loss':1,'loss':0};informative={r['id'] for r in roots if r['group']=='endgame' and len({cat[m['category']] for m in labels[r['id']]['moves']})>1}
 extra={'endgame_informative_roots':len(informative),'informative_accuracy':{},'tactics_mate_alternatives':{},'fixed_depth_paired_vs_baseline':{}}
 for budget in ['0.05','0.2']:
  extra['informative_accuracy'][budget]={};extra['tactics_mate_alternatives'][budget]={}
  for mode in NAMES:
   rs=[r for r in rows if r['budget']==float(budget) and r['mode']==mode and r['id'] in informative];extra['informative_accuracy'][budget][mode]=statistics.mean(r['quality'] for r in rs)
   # Supplemental check accepts alternate immediate mates, leaving the primary supplied-move metric unchanged.
   import chess
   ts=[r for r in rows if r['budget']==float(budget) and r['mode']==mode and r['group']=='tactics'];correct=0
   byid={r['id']:r for r in roots}
   for r in ts:
    b=chess.Board(byid[r['id']]['fen']);b.push_uci(r['uci']);correct+=int(r['quality']==1 or b.is_checkmate())
   extra['tactics_mate_alternatives'][budget][mode]=correct/len(ts)
 depthrows=[json.loads(x) for x in (OUT/'depth_controls.jsonl').read_text().splitlines()]
 for mode in NAMES:
  base={r['id']:r for r in depthrows if r['mode']=='baseline' and r['completed_depth']==2};rs=[r for r in depthrows if r['mode']==mode and r['completed_depth']==2 and r['id'] in base]
  extra['fixed_depth_paired_vs_baseline'][mode]={'paired_completed':len(rs),'mean_time_ratio':statistics.mean(r['seconds']/base[r['id']]['seconds'] for r in rs) if rs else None,'mean_node_ratio':statistics.mean(r['nodes']/base[r['id']]['nodes'] for r in rs) if rs else None}
 from run_search_integration import boot
 games=[json.loads(x) for x in (OUT/'games.jsonl').read_text().splitlines()]
 extra['game_score_bootstrap']={}
 for mode in gs['modes']:
  rs=[r for r in games if r['candidate']==mode];starts=sorted({r['start_id'] for r in rs})
  root_scores=[statistics.mean(r['points'] for r in rs if r['start_id']==p) for p in starts if all(r['points'] is not None for r in rs if r['start_id']==p)]
  extra['game_score_bootstrap'][mode]=boot(root_scores) if root_scores else None
 (OUT/'additional_summary.json').write_text(json.dumps(extra,indent=2)+'\n')
 print('Wrote results_search_integration_v1/additional_summary.json')
if __name__=='__main__':main()
