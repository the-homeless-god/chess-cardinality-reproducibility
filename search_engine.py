"""Common full-width search; experimental rules alter root quiet-move order only."""
import json,signal,time
from pathlib import Path
import chess
from run_scenario_policies import candidate_metrics,observed_class,inferred_class,choose
from run_ga_experiment import norm_features,material,counts_2
ROOT=Path(__file__).parent
MODES=('baseline','A','B','ABC','observed','inferred','GA2','cascade')
MATE=100000;INF=1000000
VALUES={chess.PAWN:100,chess.KNIGHT:320,chess.BISHOP:330,chess.ROOK:500,chess.QUEEN:900,chess.KING:0}
RUNS=json.loads((ROOT/'results_ga_2025_03/runs.json').read_text())
WEIGHTS={m:next(r['weights'] for r in RUNS if r['mode']==mode and r['seed']==100) for m,mode in [('GA2','GA2'),('cascade','GA0+GA1+GA2')]}
class Deadline(Exception):pass
def alarm(*_):raise Deadline()
def evaluate(b):
 white=0
 for sq,p in b.piece_map().items():
  f=chess.square_file(sq);r=chess.square_rank(sq);advance=r if p.color else 7-r
  center=7-(abs(2*f-7)+abs(2*r-7))/2
  bonus=0
  if p.piece_type==chess.PAWN:bonus=6*advance-2*abs(f-3.5)
  elif p.piece_type==chess.KNIGHT:bonus=8*center
  elif p.piece_type==chess.BISHOP:bonus=4*center
  elif p.piece_type==chess.ROOK:bonus=2*advance
  elif p.piece_type==chess.KING:
   nonpawns=sum(len(b.pieces(t,chess.WHITE))+len(b.pieces(t,chess.BLACK)) for t in [chess.KNIGHT,chess.BISHOP,chess.ROOK,chess.QUEEN])
   bonus=4*center if nonpawns<=2 else -4*center
  white+=(VALUES[p.piece_type]+bonus)*(1 if p.color else -1)
 return int(white if b.turn else -white)
def policy_order(board,mode,previous=None,last=None):
 b=board.copy(stack=False)
 if mode=='baseline':return {}
 if mode=='A':
  ranks={}
  for m in sorted(b.legal_moves,key=lambda m:m.uci()):
   b.push(m)
   try:ranks[m.uci()]=(-b.legal_moves.count(),)
   finally:b.pop()
  return ranks
 if mode in ['GA2','cascade']:
  side=b.turn;before=material(b,side);raw=[];moves=sorted(b.legal_moves,key=lambda m:m.uci())
  for m in moves:
   b.push(m)
   try:
    sig,uni=counts_2(b)
    raw.append([material(b,side)-before,b.legal_moves.count(),sig,uni,int(b.is_check()),int(bool(m.promotion))])
   finally:b.pop()
  return {m.uci():(sum(x*w for x,w in zip(xs,WEIGHTS[mode])),) for m,xs in zip(moves,norm_features(raw))}
 metrics,_=candidate_metrics(b)
 if mode=='B':return {x['uci']:(x['worst_own_moves_after_reply'],) for x in metrics}
 cls='neutral'
 if previous is not None and last:
  prev=previous.copy(stack=False)
  if mode=='observed':cls=observed_class(prev,b)[0]
  elif mode=='inferred':cls=inferred_class(prev,last)[0]
 order=('B','C','A') if cls=='A' else ('A','B','C')
 ranks={}
 for x in metrics:
  key=[int(x['mate_now']),int(not x['opponent_mate_in_one'])]
  for letter in order:
   v=x[letter+'_improvement'];key.extend([int(v>0),max(0,v)])
  key.extend([-x['opponent_moves'],x['worst_own_moves_after_reply'],-x['worst_mobility_gap']]);ranks[x['uci']]=tuple(key)
 return ranks
class Search:
 def __init__(self,b,mode):
  self.b=b;self.mode=mode;self.nodes=0;self.qnodes=0;self.cutoffs=0;self.killers={};self.history={};self.ranks={};self.pv=None;self.stage='features';self.deadline=None
 def check_clock(self):
  if self.deadline is not None and time.perf_counter()>=self.deadline:raise Deadline()
 def order(self,moves,ply):
  self.check_clock();b=self.b
  def key(m):
   u=m.uci();p=b.piece_at(m.to_square);victim=VALUES[p.piece_type] if p else (100 if b.is_en_passant(m) else 0)
   actor=b.piece_at(m.from_square);tactical=bool(victim or m.promotion)
   return (int(ply==0 and u==self.pv),int(tactical),victim*10-VALUES[actor.piece_type]+(VALUES.get(m.promotion,0) if m.promotion else 0) if tactical else 0,self.ranks.get(u,()) if ply==0 else (),int(u in self.killers.get(ply,[])),self.history.get(u,0))
  return sorted(sorted(moves,key=lambda m:m.uci()),key=key,reverse=True)
 def draw(self):return self.b.is_insufficient_material() or self.b.halfmove_clock>=100 or self.b.is_repetition(3)
 def negamax(self,depth,alpha,beta,ply,qleft=6):
  self.check_clock();self.nodes+=1;b=self.b
  moves=list(b.legal_moves)
  if not moves:return -MATE+ply if b.is_check() else 0
  if self.draw():return 0
  if depth<=0:
   self.qnodes+=1;check=b.is_check()
   if qleft<=0:return evaluate(b)
   if not check:
    stand=evaluate(b)
    if stand>=beta:return stand
    alpha=max(alpha,stand)
    moves=[m for m in moves if b.is_capture(m) or m.promotion]
   moves=self.order(moves,ply)
   for m in moves:
    b.push(m)
    try:s=-self.negamax(0,-beta,-alpha,ply+1,qleft-1)
    finally:b.pop()
    if s>=beta:self.cutoffs+=1;return s
    alpha=max(alpha,s)
   return alpha
  best=-INF
  for m in self.order(moves,ply):
   capture=b.is_capture(m);b.push(m)
   try:s=-self.negamax(depth-1,-beta,-alpha,ply+1)
   finally:b.pop()
   best=max(best,s);alpha=max(alpha,s)
   if alpha>=beta:
    self.cutoffs+=1
    if not capture and not m.promotion:
     u=m.uci();self.killers[ply]=[u]+[x for x in self.killers.get(ply,[]) if x!=u][:1];self.history[u]=self.history.get(u,0)+depth*depth
    break
  return best
 def root(self,depth):
  alpha=-INF;best=-INF;choice=None
  for m in self.order(list(self.b.legal_moves),0):
   self.b.push(m)
   try:s=-self.negamax(depth-1,-INF,-alpha,1)
   finally:self.b.pop()
   if s>best:best,choice=s,m.uci()
   alpha=max(alpha,s)
  return choice,best

def search(board,mode,budget,previous=None,last=None,fixed_depth=None):
 start=time.perf_counter();b=board.copy(stack=True);moves=sorted(b.legal_moves,key=lambda m:m.uci())
 if not moves:raise ValueError('terminal board')
 worker=Search(b,mode);chosen=moves[0].uci();score=None;depth=0;order_done=False;feature_seconds=None;interrupted=None;trace=[]
 old_handler=signal.signal(signal.SIGALRM,alarm)
 remaining=budget-(time.perf_counter()-start)
 try:
  if remaining<=0:raise Deadline()
  signal.setitimer(signal.ITIMER_REAL,remaining)
  try:
   fstart=time.perf_counter();worker.ranks=policy_order(b,mode,previous,last);feature_seconds=time.perf_counter()-fstart;order_done=True
   signal.setitimer(signal.ITIMER_REAL,0);worker.deadline=start+budget;worker.stage='search'
   for d in range(1,(fixed_depth or 64)+1):
    u,value=worker.root(d);chosen,score,depth=u,value,d;worker.pv=u;trace.append({'depth':d,'uci':u,'score':value,'elapsed':time.perf_counter()-start,'nodes':worker.nodes})
    if fixed_depth and d==fixed_depth:break
    if abs(value)>=MATE-1000:break
  except Deadline:interrupted=worker.stage
 except Deadline:interrupted='setup'
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
 elapsed=time.perf_counter()-start
 if feature_seconds is None:feature_seconds=elapsed
 assert b.fen()==board.fen(),(mode,b.fen(),board.fen())
 assert chess.Move.from_uci(chosen) in board.legal_moves
 return {'mode':mode,'uci':chosen,'score':score,'seconds':elapsed,'budget':budget,'completed_depth':depth,'nodes':worker.nodes,'qnodes':worker.qnodes,'cutoffs':worker.cutoffs,'feature_seconds':feature_seconds,'ordering_completed':order_done,'fallback':depth==0,'interrupted_stage':interrupted,'overrun_seconds':max(0,elapsed-budget),'trace':trace}
