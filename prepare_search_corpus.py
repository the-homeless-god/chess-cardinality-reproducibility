"""Freeze search roots from official sources before search results exist."""
import csv,hashlib,io,json,urllib.request
from pathlib import Path
import chess,chess.pgn,zstandard
ROOT=Path(__file__).parent
OUT=ROOT/'data/search_integration_v1'
SEED='20261011-search-v1'
def digest(b):return hashlib.sha256(b).hexdigest()
def rank(s):return digest((SEED+'|'+s).encode())
def dump(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 if OUT.exists():raise FileExistsError(OUT)
 OUT.mkdir()
 exclude={r['fen'] for d in ['2025_03','2025_04','2025_05_games'] for r in csv.DictReader((ROOT/f'data/endgame_corpus_{d}/positions.csv').open())}
 rows=[]
 april=list(csv.DictReader((ROOT/'data/endgame_corpus_2025_04/positions.csv').open()))
 for pieces in range(3,8):
  pool=sorted([r for r in april if int(r['pieces'])==pieces and chess.Board(r['fen']).outcome(claim_draw=True) is None],key=lambda r:rank(r['fen']))[:6]
  for r in pool:rows.append(dict(r,group='endgame',id=r['position_id'],rank=rank(r['fen'])))
 url='https://database.lichess.org/lichess_db_puzzle.csv.zst'
 req=urllib.request.Request(url,headers={'Range':'bytes=0-1048575'})
 with urllib.request.urlopen(req,timeout=60) as r:
  metadata={'url':url,'etag':r.headers.get('ETag'),'last_modified':r.headers.get('Last-Modified')}; compressed=r.read(1048576)
 (OUT/'puzzle-source-prefix.csv').write_text('')
 reader=zstandard.ZstdDecompressor().stream_reader(io.BytesIO(compressed))
 lines=io.TextIOWrapper(reader)
 prefix=[]
 for _ in range(2001):prefix.append(next(lines))
 raw=''.join(prefix);(OUT/'puzzle-source-prefix.csv').write_text(raw)
 metadata.update(compressed_prefix_bytes=len(compressed),compressed_prefix_sha256=digest(compressed),csv_prefix_rows=2000,csv_prefix_sha256=digest(raw.encode()),license='CC0',scope='first 2000 rows, not whole database')
 candidates=[]
 for r in csv.DictReader(io.StringIO(raw)):
  b=chess.Board(r['FEN']);moves=r['Moves'].split()
  if not b.is_valid() or len(moves)<2:continue
  if chess.Move.from_uci(moves[0]) not in b.legal_moves:continue
  previous=b.fen();b.push_uci(moves[0]);fen=b.fen()
  if len(b.piece_map())<10 or fen in exclude or b.outcome() is not None:continue
  check=b.copy()
  for u in moves[1:]:
   if chess.Move.from_uci(u) not in check.legal_moves:raise ValueError(r['PuzzleId'])
   check.push_uci(u)
  candidates.append({'id':'P-'+r['PuzzleId'],'group':'tactics','fen':fen,'previous_fen':previous,'last_move_uci':moves[0],'solution':moves[1:],'themes':r['Themes'],'rating':r['Rating'],'game_url':r['GameUrl'],'rank':rank(r['PuzzleId'])})
 seen=set();selected=[]
 for r in sorted(candidates,key=lambda r:r['rank']):
  game=r['game_url'].split('#')[0]
  if game in seen:continue
  seen.add(game);selected.append(r)
  if len(selected)==30:break
 assert len(selected)==30;rows+=selected
 url='https://database.lichess.org/broadcast/lichess_db_broadcast_2025-06.pgn.zst'
 with urllib.request.urlopen(url,timeout=90) as r: compressed=r.read();meta={'url':url,'etag':r.headers.get('ETag'),'last_modified':r.headers.get('Last-Modified')}
 actual=digest(compressed)
 with urllib.request.urlopen('https://database.lichess.org/broadcast/sha256sums.txt',timeout=60) as r:sums=r.read().decode()
 expected=next(line.split()[0] for line in sums.splitlines() if line.endswith('lichess_db_broadcast_2025-06.pgn.zst'))
 assert actual==expected,(actual,expected)
 pgn=zstandard.ZstdDecompressor().stream_reader(io.BytesIO(compressed));stream=io.TextIOWrapper(pgn);candidates=[];games=0
 while g:=chess.pgn.read_game(stream):
  games+=1
  if g.errors or g.headers.get('Variant','Standard')!='Standard':continue
  b=g.board()
  for ply,m in enumerate(g.mainline_moves(),1):
   old=b.fen();b.push(m)
   if ply==40:
    if len(b.piece_map())>=16 and b.is_valid() and b.outcome() is None and b.fen() not in exclude:
     game=g.headers.get('GameURL') or f'index:{games}'
     candidates.append({'id':f'M-{games:05d}','group':'middlegame','fen':b.fen(),'previous_fen':old,'last_move_uci':m.uci(),'game_url':game,'game_date':g.headers.get('Date'),'headers':dict(g.headers),'rank':rank(game+'|'+b.fen())})
    break
 selected=[];seen=set()
 for r in sorted(candidates,key=lambda r:r['rank']):
  if r['game_url'] in seen:continue
  seen.add(r['game_url']);selected.append(r)
  if len(selected)==30:break
 assert len(selected)==30;rows+=selected
 meta.update(sha256=actual,official_sha256=expected,bytes=len(compressed),games=games,candidates=len(candidates),license='CC BY-SA 4.0')
 # Cache PGNs only for chosen complete games, retaining source attribution.
 wanted={r['game_url'] for r in selected};stream=io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(io.BytesIO(compressed)));games=0;pg=[]
 while g:=chess.pgn.read_game(stream):
  games+=1
  if (g.headers.get('GameURL') or f'index:{games}') in wanted:pg.append(str(g))
 (OUT/'selected-source-games.pgn').write_text('\n\n'.join(pg)+'\n')
 prefixes={}
 for path in sorted((ROOT/'data/openings').glob('*.tsv')):
  for r in csv.DictReader(path.open(),delimiter='\t'):
   game=chess.pgn.read_game(io.StringIO(r['pgn']));ms=[m.uci() for m in game.mainline_moves()]
   if len(ms)>=8:prefixes.setdefault(' '.join(ms[:8]),{'name':r.get('name'),'eco':r.get('eco')})
 chosen=sorted(prefixes,key=rank)[:4]
 starts=[{'id':'initial','moves':[]}]+[{'id':f'opening-{i+1}','moves':p.split(),**prefixes[p]} for i,p in enumerate(chosen)]
 dump('positions.json',rows);dump('game_starts.json',starts)
 dump('manifest.json',{'seed':SEED,'roots':len(rows),'group_counts':{k:sum(r['group']==k for r in rows) for k in ['endgame','tactics','middlegame']},'puzzles':metadata,'broadcast':meta,'positions_sha256':digest((OUT/'positions.json').read_bytes()),'script_sha256':digest(Path(__file__).read_bytes()),'labels_used_for_selection':False})
 print('Frozen',len(rows),'roots and',len(starts),'paired starts',flush=True)
if __name__=='__main__':main()
