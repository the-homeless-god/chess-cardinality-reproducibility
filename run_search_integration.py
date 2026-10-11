"""Paired equal-time search ablations. Never supply reference labels to search."""
import argparse,collections,csv,hashlib,json,platform,random,statistics,sys,time
from pathlib import Path
import chess,chess.engine,chess.pgn
from search_engine import search,MODES,WEIGHTS
ROOT=Path(__file__).parent;DATA=ROOT/'data/search_integration_v1';OUT=ROOT/'results_search_integration_v1'
SCORE={'win':2,'cursed-win':1,'draw':1,'blessed-loss':1,'loss':0}
def dump(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def loadlines(path):return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
def append(name,r):
 with (OUT/name).open('a') as f:f.write(json.dumps(r,ensure_ascii=False)+'\n');f.flush()
def boot(xs):
 rng=random.Random(20261011);vals=sorted(statistics.mean(rng.choices(xs,k=len(xs))) for _ in range(10000))
 return {'mean':statistics.mean(xs),'ci95':[vals[250],vals[9749]],'n_roots':len(xs)}
def engine_reference(path,roots):
 existing=loadlines(OUT/'references.jsonl');done={r['id'] for r in existing}
 with chess.engine.SimpleEngine.popen_uci(path) as engine:
  engine.configure({'Threads':1,'Hash':16,'SyzygyPath':''})
  for i,r in enumerate(roots):
   if r['group']=='endgame' or r['id'] in done:continue
   b=chess.Board(r['fen']);engine.configure({'Clear Hash':None});start=time.perf_counter()
   infos=engine.analyse(b,chess.engine.Limit(nodes=100000),multipv=b.legal_moves.count())
   scores={p['pv'][0].uci():p['score'].pov(b.turn).score(mate_score=10000) for p in infos}
   assert set(scores)=={m.uci() for m in b.legal_moves}
   append('references.jsonl',{'id':r['id'],'fen':r['fen'],'scores':scores,'reference_moves':[u for u,v in scores.items() if v==max(scores.values())],'max_score':max(scores.values()),'nodes':max(p.get('nodes',0) for p in infos),'min_depth':min(p.get('depth',0) for p in infos),'seconds':time.perf_counter()-start,'requested_nodes':100000,'multipv':len(scores)})
   print('reference',i+1,r['id'],flush=True)
def trials(roots):
 done={(r['id'],r['mode'],r['budget'],r['repeat']) for r in loadlines(OUT/'trials.jsonl')}
 for rep in range(2):
  for bi,budget in enumerate([.05,.2]):
   for i,r in enumerate(roots):
    shift=(i+bi+rep)%len(MODES);order=MODES[shift:]+MODES[:shift]
    for mode in order:
     if (r['id'],mode,budget,rep) in done:continue
     result=search(chess.Board(r['fen']),mode,budget,chess.Board(r['previous_fen']),r['last_move_uci'])
     append('trials.jsonl',{'id':r['id'],'group':r['group'],'repeat':rep,**result})
    if (i+1)%10==0:print('trials',rep,budget,i+1,flush=True)
def depths(roots):
 subset=[r for group in ['endgame','tactics','middlegame'] for r in sorted([r for r in roots if r['group']==group],key=lambda x:x['rank'])[:4]]
 done={(r['id'],r['mode']) for r in loadlines(OUT/'depth_controls.jsonl')}
 for r in subset:
  for mode in MODES:
   if (r['id'],mode) in done:continue
   result=search(chess.Board(r['fen']),mode,5,chess.Board(r['previous_fen']),r['last_move_uci'],fixed_depth=2)
   append('depth_controls.jsonl',{'id':r['id'],'group':r['group'],'requested_depth':2,**result})
  print('fixed depth',r['id'],flush=True)
def games():
 starts=json.loads((DATA/'game_starts.json').read_text());modes=[m for m in MODES if m!='GA2']
 done={(r['start_id'],r['candidate'],r['candidate_color']) for r in loadlines(OUT/'games.jsonl')}
 for si,start in enumerate(starts):
  order=modes[si%len(modes):]+modes[:si%len(modes)]
  for mode in order:
   for color in [chess.WHITE,chess.BLACK]:
    if (start['id'],mode,color) in done:continue
    b=chess.Board();prefix=start['moves']
    for u in prefix:b.push_uci(u)
    trace=[]
    while b.outcome(claim_draw=True) is None and len(trace)<240:
     previous=b.copy();last=None
     if previous.move_stack:last=previous.pop().uci()
     player=mode if b.turn==color else 'baseline'
     result=search(b,player,.025,previous if last else None,last);b.push_uci(result['uci']);trace.append(result)
    out=b.outcome(claim_draw=True);points=None if out is None else (.5 if out.winner is None else float(out.winner==color))
    rec={'start_id':start['id'],'candidate':mode,'candidate_color':color,'prefix':prefix,'moves':[r['uci'] for r in trace],'trace':trace,'result':out.result() if out else '*','termination':out.termination.name if out else '240_ply_cutoff_unresolved','points':points,'plies':len(trace),'final_fen':b.fen()}
    append('games.jsonl',rec)
    g=chess.pgn.Game.from_board(b);g.headers['Event']='Equal-time root-ordering ablation';g.headers['White']=mode if color else 'baseline';g.headers['Black']='baseline' if color else mode;g.headers['Result']=rec['result'];g.headers['TimeControl']='25ms/move';g.headers['StartId']=start['id']
    with (OUT/'games.pgn').open('a') as f:f.write(str(g)+'\n\n')
    print('game',start['id'],mode,'white' if color else 'black',rec['result'],rec['termination'],len(trace),flush=True)
def summarize(roots):
 refs={r['id']:r for r in loadlines(OUT/'references.jsonl')}; labels={r['position_id']:r['response'] for r in loadlines(ROOT/'results_scenarios_2025_04/responses.jsonl')};byid={r['id']:r for r in roots}
 rows=loadlines(OUT/'trials.jsonl')
 for r in rows:
  source=byid[r['id']];u=r['uci']
  if r['group']=='endgame':
   scores={m['uci']:2-SCORE[m['category']] for m in labels[r['id']]['moves']};r['quality']=float(scores[u]==max(scores.values()));r['regret']=max(scores.values())-scores[u]
  elif r['group']=='tactics':r['quality']=float(u==source['solution'][0]);r['regret']=refs[r['id']]['max_score']-refs[r['id']]['scores'][u]
  else:
   ref=refs[r['id']];r['quality']=float(u in ref['reference_moves']);r['regret']=ref['max_score']-ref['scores'][u]
 dump('scored_trials.json',rows)
 summary={'trials':len(rows),'roots':len(roots),'modes':{},'paired_vs_baseline':{},'quality_semantics':{'endgame':'exact best-category preservation','tactics':'supplied first solution match, alternatives possible','middlegame':'approximate 100k-total-node MultiPV agreement/regret'}}
 for budget in [.05,.2]:
  key=str(budget);summary['modes'][key]={};summary['paired_vs_baseline'][key]={}
  for group in ['endgame','tactics','middlegame']:
   summary['modes'][key][group]={};summary['paired_vs_baseline'][key][group]={}
   rootids=[r['id'] for r in roots if r['group']==group]
   group_rows=[r for r in rows if r['budget']==budget and r['group']==group]
   def root_mean(mode,p,field):return statistics.mean(r[field] for r in group_rows if r['mode']==mode and r['id']==p)
   for mode in MODES:
    rs=[r for r in group_rows if r['mode']==mode]
    summary['modes'][key][group][mode]={'trials':len(rs),'quality':statistics.mean(r['quality'] for r in rs),'regret':statistics.mean(r['regret'] for r in rs),'depth':statistics.mean(r['completed_depth'] for r in rs),'nodes':statistics.mean(r['nodes'] for r in rs),'seconds':statistics.mean(r['seconds'] for r in rs),'feature_seconds':statistics.mean(r['feature_seconds'] for r in rs),'fallbacks':sum(r['fallback'] for r in rs),'feature_timeouts':sum(not r['ordering_completed'] for r in rs),'max_overrun':max(r['overrun_seconds'] for r in rs)}
    if mode!='baseline':summary['paired_vs_baseline'][key][group][mode]={field:boot([root_mean(mode,p,field)-root_mean('baseline',p,field) for p in rootids]) for field in ['quality','regret','completed_depth','nodes']}
 dump('summary.json',summary)
 ds=loadlines(OUT/'depth_controls.jsonl');different=[]
 for rid in {r['id'] for r in ds}:
  rs=[r for r in ds if r['id']==rid and r['completed_depth']==2]
  if len({r['score'] for r in rs})>1:different.append(rid)
 assert not different,different
 depthsum={'rows':len(ds),'score_disagreements':different,'modes':{m:{'completed':sum(r['completed_depth']==2 for r in ds if r['mode']==m),'seconds_mean':statistics.mean(r['seconds'] for r in ds if r['mode']==m),'nodes_mean':statistics.mean(r['nodes'] for r in ds if r['mode']==m)} for m in MODES}}
 dump('depth_summary.json',depthsum)
 gs=loadlines(OUT/'games.jsonl');gamesum={'games':len(gs),'budget_seconds':.025,'max_plies':240,'modes':{}}
 for m in [m for m in MODES if m!='GA2']:
  rs=[r for r in gs if r['candidate']==m];points=sum(r['points'] for r in rs if r['points'] is not None);unresolved=sum(r['points'] is None for r in rs);times=[x['seconds'] for r in rs for x in r['trace'] if x['mode']==m]
  gamesum['modes'][m]={'games':len(rs),'wins':sum(r['points']==1 for r in rs),'draws':sum(r['points']==.5 for r in rs),'losses':sum(r['points']==0 for r in rs),'unresolved':unresolved,'known_points':points,'score_bounds':[points/len(rs),(points+unresolved)/len(rs)],'candidate_fallbacks':sum(x['fallback'] for r in rs for x in r['trace'] if x['mode']==m),'candidate_moves':len(times),'candidate_mean_seconds':statistics.mean(times),'terminations':dict(collections.Counter(r['termination'] for r in rs))}
 dump('games_summary.json',gamesum)
 print('Summaries complete',len(rows),'trials;',len(gs),'games',flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--engine');p.add_argument('--stage',choices=['reference','trials','depth','games','summary','all'],default='all');a=p.parse_args();OUT.mkdir(exist_ok=True)
 roots=json.loads((DATA/'positions.json').read_text())
 env={'python':sys.version,'chess':chess.__version__,'platform':platform.platform(),'machine':platform.machine(),'protocol_sha256':hashlib.sha256((ROOT/'search-integration-protocol.md').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'search_sha256':hashlib.sha256((ROOT/'search_engine.py').read_bytes()).hexdigest(),'positions_sha256':hashlib.sha256((DATA/'positions.json').read_bytes()).hexdigest(),'weights':WEIGHTS,'workstation_isolated':False,'wall_budget_includes_features':True}
 if a.engine:env.update(engine_sha256=hashlib.sha256(Path(a.engine).read_bytes()).hexdigest(),engine_options={'Threads':1,'Hash':16,'SyzygyPath':''},engine_release='sf_17.1')
 if not (OUT/'environment.json').exists():dump('environment.json',env)
 if a.stage in ['reference','all']:engine_reference(a.engine,roots)
 if a.stage in ['trials','all']:trials(roots)
 if a.stage in ['depth','all']:depths(roots)
 if a.stage in ['games','all']:games()
 if a.stage in ['summary','all']:summarize(roots)
if __name__=='__main__':main()
