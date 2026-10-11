"""Offline independent verification of release hashes, move labels and traces."""
import collections,csv,hashlib,json,statistics
from pathlib import Path
import chess
ROOT=Path(__file__).parent
SCORE={'win':2,'cursed-win':1,'draw':1,'blessed-loss':1,'loss':0}
def main():
 manifest=ROOT/'checksums.json'
 if manifest.exists():
  for name,digest in json.loads(manifest.read_text()).items():
   assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
  print('All release checksums match')
 labels={r['position_id']:r for r in map(json.loads,(ROOT/'results_scenarios_2025_04/responses.jsonl').read_text().splitlines())}
 rows=list(map(json.loads,(ROOT/'results_extended/april_rows.jsonl').read_text().splitlines()));summary=json.loads((ROOT/'results_extended/april_summary.json').read_text())
 assert len(rows)==250 and sum(r['informative'] for r in rows)==126
 for r in rows:
  b=chess.Board(r['fen']);scores={m['uci']:2-SCORE[m['category']] for m in labels[r['position_id']]['response']['moves']}
  assert set(scores)=={m.uci() for m in b.legal_moves}
  for mode,us in r['choices'].items():
   assert all(chess.Move.from_uci(u) in b.legal_moves for u in us)
   assert abs(statistics.mean(scores[u]==max(scores.values()) for u in us)-r['accuracy'][mode])<1e-12
 for m,s in summary['modes'].items():
  assert abs(statistics.mean(r['accuracy'][m] for r in rows)-s['accuracy'])<1e-12
 games=list(map(json.loads,(ROOT/'results_extended/stockfish_games.jsonl').read_text().splitlines()));gs=json.loads((ROOT/'results_extended/stockfish_games_summary.json').read_text())
 assert len(games)==540 and len({r['position_id'] for r in games})==45
 for g in games:
  b=chess.Board(g['fen']);color=b.turn if g['candidate_starts'] else not b.turn
  assert b.outcome(claim_draw=True) is None
  for u in g['moves']:
   m=chess.Move.from_uci(u);assert m in b.legal_moves;(b.push(m))
  out=b.outcome(claim_draw=True)
  assert len(g['moves'])==g['plies']
  assert out is not None and out.termination.name==g['termination']
  assert g['score']==(.5 if out.winner is None else float(out.winner==color))
 for m,s in gs['modes'].items():
  rs=[g for g in games if g['candidate']==m]
  assert len(rs)==s['games'] and sum(g['score'] for g in rs)==s['points']
 print('April: all labels, legal choices and accuracies verified')
 print('May: all 540 complete traces, terminations and scores verified')
 controls=json.loads((ROOT/'results_extended/control_runs.json').read_text());features=json.loads((ROOT/'results_ga_2025_03/features.json').read_text());test=[r for r in features if r['split']=='test']
 for run in controls:
  for r in test:
   j=max(range(len(r['moves'])),key=lambda j:(sum(a*b for a,b in zip(run['weights'],r['features'][j])),-j))
   assert j==run['test_choices'][r['id']]
 print('March control decisions independently recomputed')
if __name__=='__main__':main()
