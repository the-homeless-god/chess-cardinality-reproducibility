"""Exploratory frozen-model controls; see extended-comparison-protocol.md."""
from pathlib import Path
import argparse, collections, csv, hashlib, json, platform, random, signal, statistics, sys, time
import chess, chess.engine
from run_ga_experiment import GA, CONFIGS, SEEDS, choice, fitness, accuracy, material, counts_2, norm_features
from run_full_games import make_move, alarm_handler, MoveTimeout
ROOT=Path(__file__).parent
OUT=ROOT/'results_extended'
SCORE={'win':2,'cursed-win':1,'draw':1,'blessed-loss':1,'loss':0}
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def boot(xs):
    rng=random.Random(20261011)
    vals=sorted(sum(rng.choices(xs,k=len(xs)))/len(xs) for _ in range(10000))
    return {'mean':statistics.mean(xs),'ci95':[vals[250],vals[9749]],'roots':len(xs)}
def fit_controls():
    data=json.loads((ROOT/'results_ga_2025_03/features.json').read_text())
    tr=[r for r in data if r['split']=='train']; va=[r for r in data if r['split']=='val']; te=[r for r in data if r['split']=='test']
    runs=[]
    for seed in SEEDS:
        start=time.perf_counter(); ga=GA(seed,CONFIGS[1],tr,va); plateau=0; old=-1
        for _ in range(50):
            ga.generation()
            plateau=0 if ga.best_val>old else plateau+1; old=ga.best_val
            if ga.best_val>=.90 and plateau>=3: break
        runs.append({'mode':'GA2_early_stop','seed':seed,'weights':ga.best_weights,'fitness_evaluations':ga.evaluations,'validation_evaluations':ga.val_evaluations,'seconds':time.perf_counter()-start})
        start=time.perf_counter(); rng=random.Random(seed); bestkey=(-1,-1); best=None
        for _ in range(50):
            population=[[rng.uniform(-2,2) for _ in range(6)] for _ in range(12)]
            f,w=max(((fitness(tr,w),w) for w in population),key=lambda x:x[0])
            key=(accuracy(va,w),f)
            if key>bestkey: bestkey,best=key,w
        runs.append({'mode':'random_weight_search','seed':seed,'weights':best,'fitness_evaluations':600,'validation_evaluations':50,'seconds':time.perf_counter()-start})
        print('fit',seed,flush=True)
    for r in runs: r['test_choices']={p['id']:choice(p,r['weights']) for p in te}
    save('control_runs.json',runs)
    oldruns=json.loads((ROOT/'results_ga_2025_03/runs.json').read_text())
    groups={m:[r for r in runs+oldruns if r['mode']==m] for m in ['GA2','GA1+GA2','GA0+GA1+GA2','GA2_early_stop','random_weight_search']}
    summaries={}; vectors={}
    for m,rs in groups.items():
        xs=[statistics.mean(p['scores'][r['test_choices'][p['id']]]==p['best'] for r in rs) for p in te]
        vectors[m]=xs
        summaries[m]={'accuracy':statistics.mean(xs),'informative_accuracy':statistics.mean(x for x,p in zip(xs,te) if p['informative']),'mean_evaluations':statistics.mean(r['fitness_evaluations'] for r in rs),'mean_fit_seconds':statistics.mean(r['seconds'] for r in rs)}
    save('control_summary.json',{'modes':summaries,'paired_cascade_minus':{m:boot([a-b for a,b in zip(vectors['GA0+GA1+GA2'],xs)]) for m,xs in vectors.items() if m!='GA0+GA1+GA2'},'timing_warning':'Existing modes were timed in earlier executions; across-date fitting times are descriptive, not paired benchmarks.'})
def raw_row(board):
    side=board.turn; before=material(board,side); moves=sorted(m.uci() for m in board.legal_moves); raw=[]
    for u in moves:
        move=chess.Move.from_uci(u); board.push(move); sig,uni=counts_2(board)
        raw.append([material(board,side)-before,board.legal_moves.count(),sig,uni,int(board.is_check()),int(bool(move.promotion))]); board.pop()
    return {'moves':moves,'raw':raw,'features':norm_features(raw)}
def greedy(board):
    side=board.turn
    def value(u):
        board.push(chess.Move.from_uci(u)); v=material(board,side); board.pop(); return v
    return max(sorted(m.uci() for m in board.legal_moves),key=value)
def sf_move(engine,board,nodes):
    engine.configure({'Clear Hash':None})
    start=time.perf_counter(); info=engine.analyse(board,chess.engine.Limit(nodes=nodes))
    return info['pv'][0].uci(),time.perf_counter()-start,info.get('nodes'),info.get('depth')
def april(engine):
    preds=json.loads((ROOT/'results_scenarios_2025_04/predictions.json').read_text())
    labels={r['position_id']:r['response'] for r in map(json.loads,(ROOT/'results_scenarios_2025_04/responses.jsonl').read_text().splitlines())}
    runs=[r for r in json.loads((ROOT/'results_ga_2025_03/runs.json').read_text()) if r['mode']=='GA0+GA1+GA2']
    rows=[]
    with (OUT/'april_rows.jsonl').open('w') as file:
        for pred in preds:
            board=chess.Board(pred['fen']); label=labels[pred['position_id']]; scores={m['uci']:2-SCORE[m['category']] for m in label['moves']}; best=max(scores.values())
            start=time.perf_counter(); row=raw_row(board); featseconds=time.perf_counter()-start
            choices={m:[u] for m,u in pred['choices'].items()}; choices['material']=[greedy(board)]
            choices['cascade']=[row['moves'][choice(row,r['weights'])] for r in runs]
            timings={}
            for nodes in [1000,10000]:
                u,secs,n,dep=sf_move(engine,board,nodes); key=f'Stockfish_{nodes}'; choices[key]=[u]; timings[key]={'seconds':secs,'nodes':n,'depth':dep}
            rec={'position_id':pred['position_id'],'fen':pred['fen'],'pieces':len(board.piece_map()),'best':best,'informative':len(set(scores.values()))>1,'choices':choices,'accuracy':{m:statistics.mean(scores[u]==best for u in us) for m,us in choices.items()},'regret':{m:statistics.mean(best-scores[u] for u in us) for m,us in choices.items()},'feature_seconds':featseconds,'engine':timings,'root_category':label['category'],'root_dtz':label['dtz']}
            rows.append(rec); file.write(json.dumps(rec)+'\n'); file.flush()
            if len(rows)%25==0: print('April',len(rows),flush=True)
    modes={m:{'accuracy':statistics.mean(r['accuracy'][m] for r in rows),'informative_accuracy':statistics.mean(r['accuracy'][m] for r in rows if r['informative']),'regret':statistics.mean(r['regret'][m] for r in rows),'accuracy_by_pieces':{str(p):statistics.mean(r['accuracy'][m] for r in rows if r['pieces']==p) for p in range(3,8)}} for m in rows[0]['accuracy']}
    cats=collections.Counter(m['category'] for label in labels.values() for m in label['moves'])
    save('april_summary.json',{'roots':len(rows),'informative':sum(r['informative'] for r in rows),'modes':modes,'paired_cascade_minus':{m:boot([r['accuracy']['cascade']-r['accuracy'][m] for r in rows]) for m in ['material','min_kappa','Stockfish_1000','Stockfish_10000']},'move_categories':dict(cats),'root_dtz_available':sum(r['root_dtz'] is not None for r in rows),'engine_latency':{m:{'median_seconds':statistics.median(r['engine'][m]['seconds'] for r in rows),'mean_seconds':statistics.mean(r['engine'][m]['seconds'] for r in rows)} for m in ['Stockfish_1000','Stockfish_10000']},'cascade_feature_median_seconds':statistics.median(r['feature_seconds'] for r in rows)})
def games(engine):
    signal.signal(signal.SIGALRM,alarm_handler)
    source=list(csv.DictReader((ROOT/'data/endgame_corpus_2025_05_games/positions.csv').open()))
    roots=[r for r in source if chess.Board(r['fen']).outcome(claim_draw=True) is None]
    weights=next(r['weights'] for r in json.loads((ROOT/'results_ga_2025_03/runs.json').read_text()) if r['mode']=='GA0+GA1+GA2' and r['seed']==100)
    records=[]
    with (OUT/'stockfish_games.jsonl').open('w') as f:
        for row in roots:
            for policy in ['observed','inferred','neutral','GA0','min_kappa','material']:
                for starts in [True,False]:
                    b=chess.Board(row['fen']); prev=chess.Board(row['previous_fen']); last=row['last_move_uci']; color=b.turn if starts else not b.turn; moves=[]; timings=[]
                    while b.outcome(claim_draw=True) is None and len(moves)<200:
                        if b.turn!=color:
                            u,sec,n,dep=sf_move(engine,b,1000); timed=False; name='Stockfish_1000'
                        elif policy=='material':
                            start=time.perf_counter(); u=greedy(b.copy()); sec=time.perf_counter()-start; timed=False; name=policy
                        else:
                            u,sec,timed=make_move(policy,b,prev,last,weights); name=policy
                        assert chess.Move.from_uci(u) in b.legal_moves
                        timings.append({'policy':name,'seconds':sec,'timeout':timed}); prev=b.copy(stack=False); b.push(chess.Move.from_uci(u)); last=u; moves.append(u)
                    out=b.outcome(claim_draw=True); score=.5 if out is None or out.winner is None else float(out.winner==color)
                    rec={'position_id':row['position_id'],'fen':row['fen'],'candidate':policy,'candidate_starts':starts,'score':score,'termination':out.termination.name if out else '200_ply_cutoff','plies':len(moves),'moves':moves,'timings':timings}
                    records.append(rec); f.write(json.dumps(rec)+'\n'); f.flush()
            print('May',row['position_id'],len(records),flush=True)
    modes={}
    for m in ['observed','inferred','neutral','GA0','min_kappa','material']:
        rs=[r for r in records if r['candidate']==m]; root_scores=[statistics.mean(r['score'] for r in rs if r['position_id']==p['position_id']) for p in roots]
        ts=[t['seconds'] for r in rs for t in r['timings'] if t['policy']==m]
        modes[m]={'games':len(rs),'points':sum(r['score'] for r in rs),'wins':sum(r['score']==1 for r in rs),'draws':sum(r['score']==.5 for r in rs),'losses':sum(r['score']==0 for r in rs),'root_score':boot(root_scores),'termination':dict(collections.Counter(r['termination'] for r in rs)),'timeouts':sum(t['timeout'] for r in rs for t in r['timings']),'move_median_seconds':statistics.median(ts),'move_total_seconds':sum(ts)}
    save('stockfish_games_summary.json',{'roots':len(roots),'excluded_terminal':[r['position_id'] for r in source if r not in roots],'modes':modes,'paired_minus_min_kappa':{m:boot([statistics.mean(r['score'] for r in records if r['position_id']==p['position_id'] and r['candidate']==m)-statistics.mean(r['score'] for r in records if r['position_id']==p['position_id'] and r['candidate']=='min_kappa') for p in roots]) for m in modes if m!='min_kappa'}})
def main():
    p=argparse.ArgumentParser();p.add_argument('--engine',required=True);p.add_argument('--stage',choices=['controls','april','games','all'],default='all');args=p.parse_args(); OUT.mkdir(exist_ok=True)
    save('environment.json',{'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'chess':chess.__version__,'engine_sha256':hashlib.sha256(Path(args.engine).read_bytes()).hexdigest(),'engine_release':'sf_17.1','options':{'Threads':1,'Hash':16,'SyzygyPath':''},'protocol_sha256':hashlib.sha256((ROOT/'extended-comparison-protocol.md').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    if args.stage in ['controls','all']: fit_controls()
    if args.stage!='controls':
        with chess.engine.SimpleEngine.popen_uci(args.engine) as e:
            e.configure({'Threads':1,'Hash':16,'SyzygyPath':''})
            if args.stage in ['april','all']: april(e)
            if args.stage in ['games','all']: games(e)
if __name__=='__main__': main()
