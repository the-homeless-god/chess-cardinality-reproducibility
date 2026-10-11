"""Independent offline recomputation of new labels, summaries and legal histories."""
import argparse,collections,csv,hashlib,json,statistics,sys
from pathlib import Path
import chess,chess.pgn
ROOT=Path(__file__).parent
MODES=('baseline','A','B','ABC','observed','inferred','GA2','cascade')
SCORE={'win':2,'cursed-win':1,'draw':1,'blessed-loss':1,'loss':0}
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def close(a,b):assert abs(a-b)<1e-9,(a,b)
def main():
 p=argparse.ArgumentParser();p.add_argument('--repeat-fixed-depth',action='store_true');p.add_argument('--report');args=p.parse_args()
 data=ROOT/'data/search_integration_v1';out=ROOT/'results_search_integration_v1';manifest=json.loads((data/'manifest.json').read_text());env=json.loads((out/'environment.json').read_text())
 for name,key in [('positions.json','positions_sha256'),('game_starts.json','game_starts_sha256')]:assert hashlib.sha256((data/name).read_bytes()).hexdigest()==manifest[key]
 assert hashlib.sha256((data/'puzzle-source-prefix.csv').read_bytes()).hexdigest()==manifest['puzzles']['csv_prefix_sha256']
 assert hashlib.sha256((ROOT/'search_engine.py').read_bytes()).hexdigest()==env['search_sha256']
 assert hashlib.sha256((ROOT/'search-integration-protocol.md').read_bytes()).hexdigest()==env['protocol_sha256']
 rows=json.loads((data/'positions.json').read_text());byid={r['id']:r for r in rows};assert len(byid)==90
 for r in rows:
  b=chess.Board(r['previous_fen']);b.push_uci(r['last_move_uci']);assert b.fen()==r['fen'];assert b.is_valid() and b.outcome(claim_draw=True) is None
  if r['group']=='tactics':
   for u in r['solution']:b.push_uci(u)
 mid={};f=(data/'selected-source-games.pgn').open()
 while g:=chess.pgn.read_game(f):
  assert not g.errors;b=g.board()
  for m in list(g.mainline_moves())[:40]:b.push(m)
  mid[b.fen()]=dict(g.headers)
 assert all(r['fen'] in mid for r in rows if r['group']=='middlegame')
 # Puzzle first move and source setup checked separately, without importing selector.
 puzzles={r['PuzzleId']:r for r in csv.DictReader((data/'puzzle-source-prefix.csv').open())}
 for r in rows:
  if r['group']=='tactics':
   source=puzzles[r['id'][2:]];b=chess.Board(source['FEN']);ms=source['Moves'].split();b.push_uci(ms[0]);assert b.fen()==r['fen'] and ms[1:]==r['solution']
 labels={r['position_id']:r['response'] for r in lines(ROOT/'results_scenarios_2025_04/responses.jsonl')};refs={r['id']:r for r in lines(out/'references.jsonl')}
 assert len(refs)==60
 for r in refs.values():assert set(r['scores'])=={m.uci() for m in chess.Board(r['fen']).legal_moves};assert r['max_score']==max(r['scores'].values())
 trials=lines(out/'trials.jsonl');scored=json.loads((out/'scored_trials.json').read_text());summary=json.loads((out/'summary.json').read_text())
 assert len(trials)==len(scored)==2880
 assert len({(r['id'],r['mode'],r['budget'],r['repeat']) for r in trials})==2880
 for raw,r in zip(trials,scored):
  assert all(r[k]==v for k,v in raw.items());source=byid[r['id']];b=chess.Board(source['fen']);assert chess.Move.from_uci(r['uci']) in b.legal_moves
  assert r['fallback']==(r['completed_depth']==0)
  if r['fallback']:assert r['uci']==min(m.uci() for m in b.legal_moves)
  if r['group']=='endgame':
   vals={m['uci']:2-SCORE[m['category']] for m in labels[r['id']]['moves']};quality=float(vals[r['uci']]==max(vals.values()));regret=max(vals.values())-vals[r['uci']]
  elif r['group']=='tactics':quality=float(r['uci']==source['solution'][0]);regret=refs[r['id']]['max_score']-refs[r['id']]['scores'][r['uci']]
  else:quality=float(r['uci'] in refs[r['id']]['reference_moves']);regret=refs[r['id']]['max_score']-refs[r['id']]['scores'][r['uci']]
  close(quality,r['quality']);close(regret,r['regret'])
 for budget,groups in summary['modes'].items():
  for group,modes in groups.items():
   for mode,s in modes.items():
    rs=[r for r in scored if r['budget']==float(budget) and r['group']==group and r['mode']==mode];assert len(rs)==s['trials']==60
    for source,target in [('quality','quality'),('regret','regret'),('completed_depth','depth'),('nodes','nodes'),('seconds','seconds'),('feature_seconds','feature_seconds')]:close(statistics.mean(r[source] for r in rs),s[target])
    assert sum(r['fallback'] for r in rs)==s['fallbacks']
 ds=lines(out/'depth_controls.jsonl');assert len(ds)==96
 for rid in {r['id'] for r in ds}:assert len({r['score'] for r in ds if r['id']==rid and r['completed_depth']==2})<=1
 games=lines(out/'games.jsonl');gs=json.loads((out/'games_summary.json').read_text());assert len(games)==70
 assert len({(r['start_id'],r['candidate'],r['candidate_color']) for r in games})==70
 for r in games:
  b=chess.Board()
  for u in r['prefix']+r['moves']:b.push_uci(u)
  assert b.fen()==r['final_fen'] and len(r['moves'])==r['plies']==len(r['trace'])
  for u,t in zip(r['moves'],r['trace']):assert u==t['uci']
  actual=b.outcome(claim_draw=True)
  if actual is None:assert r['result']=='*' and r['points'] is None and r['plies']==240
  else:
   assert r['result']==actual.result() and r['termination']==actual.termination.name
   assert r['points']==(.5 if actual.winner is None else float(actual.winner==r['candidate_color']))
 for mode,s in gs['modes'].items():
  rs=[r for r in games if r['candidate']==mode];assert len(rs)==s['games']==10;assert sum(r['points'] is None for r in rs)==s['unresolved'];close(sum(r['points'] for r in rs if r['points'] is not None),s['known_points'])
  close(s['score_bounds'][0],s['known_points']/10);close(s['score_bounds'][1],(s['known_points']+s['unresolved'])/10)
 repeated=[]
 if args.repeat_fixed_depth:
  from search_engine import search
  for old in ds:
   source=byid[old['id']];new=search(chess.Board(source['fen']),old['mode'],5,chess.Board(source['previous_fen']),source['last_move_uci'],fixed_depth=2)
   if old['completed_depth']==new['completed_depth']==2:assert old['score']==new['score'] and old['uci']==new['uci'] and old['nodes']==new['nodes'],(old,new)
   repeated.append({'id':old['id'],'mode':old['mode'],'original_depth':old['completed_depth'],'repeated_depth':new['completed_depth'],'score':new['score'],'nodes':new['nodes'],'seconds':new['seconds']})
  print('Fixed-depth fresh computation:',len(repeated),'trials')
 report={'roots_verified':90,'references_verified':60,'timed_trials_verified':len(trials),'fixed_depth_rows_verified':len(ds),'games_replayed':len(games),'fresh_fixed_depth':repeated,'independent_scientific_replication':False,'python':sys.version}
 if args.report:Path(args.report).write_text(json.dumps(report,indent=2)+'\n')
 print('Verified: 90 roots, 60 references, 2880 trials, 96 depth controls, 70 legal game histories. No unresolved game counted as a draw.')
if __name__=='__main__':main()
