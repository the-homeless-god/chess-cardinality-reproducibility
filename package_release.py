"""Export only this chess subtree, without parent Git history or private evidence."""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile
ROOT=Path(__file__).parent.resolve()
EXCLUDE={'__pycache__','.git','.venv','tools','releases','.DS_Store','RELEASE_README.md','checksums.json','submission-artificial-intelligence','submission-isuct','.local-publication','figures','demo'}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--version',default='v1.2.0');parser.add_argument('--stage',type=Path,default=Path('/private/tmp/chess-cardinality-code-data-v1.2.0'));args=parser.parse_args()
 VERSION=args.version
 if not VERSION.startswith('v') or any(c not in 'v0123456789.' for c in VERSION):raise ValueError('Use a numeric v-prefixed release version')
 stage=args.stage
 archive=ROOT/'releases'/f'chess-cardinality-{VERSION}.zip'
 if archive.exists():raise FileExistsError(archive)
 if stage.exists(): raise FileExistsError(stage)
 stage.mkdir()
 for p in sorted(ROOT.rglob('*')):
  rel=p.relative_to(ROOT)
  if not p.is_file() or any(part in EXCLUDE for part in rel.parts) or p.suffix in {'.pyc','.docx','.pdf','.png','.jpg'}:continue
  if p.suffix=='.md' and p.parent==ROOT and p.name not in ['README.md', 'REPRODUCE.md', 'THIRD_PARTY_NOTICES.md', 'extended-comparison-protocol.md', 'full-game-and-runtime-protocol.md', 'ga-experiment-protocol.md', 'scenario-comparison-protocol.md', 'search-integration-protocol.md']:continue
  target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 (stage/'README.md').write_bytes((ROOT/'README.md').read_bytes())
 manifest={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
 (stage/'checksums.json').write_text(json.dumps(manifest,indent=2)+'\n')
 out=ROOT/'releases';out.mkdir(exist_ok=True);archive=out/f'chess-cardinality-{VERSION}.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(stage.rglob('*')):
   if p.is_file():z.write(p,Path(f'chess-cardinality-{VERSION}')/p.relative_to(stage))
 digest=hashlib.sha256(archive.read_bytes()).hexdigest();(out/f'SHA256SUMS-{VERSION}.txt').write_text(f'{digest}  {archive.name}\n')
 print(stage);print(archive);print(digest);print('Files',len(manifest)+1)
if __name__=='__main__':main()
