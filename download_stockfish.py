"""Fetch the exact official macOS ARM64 reference release; no binary vendoring."""
import hashlib,platform,tarfile,urllib.request
from pathlib import Path
URL='https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-macos-m1-apple-silicon.tar'
# The archive's hash is checked before extraction. Other platforms: obtain the
# matching official 17.1 asset and pass its executable via --engine.
EXPECTED='4e23165eb8f353c221ff7ab6716f0a160c3993dadf90d0c0ad982a7ade4091c9'
def main():
 if platform.system()!='Darwin' or platform.machine()!='arm64':
  raise SystemExit('Use an official Stockfish 17.1 executable for this platform and pass --engine /path/to/stockfish. See REPRODUCE.md.')
 target=Path(__file__).parent/'tools/stockfish-17.1';target.mkdir(parents=True,exist_ok=True);archive=target/'release.tar'
 urllib.request.urlretrieve(URL,archive)
 actual=hashlib.sha256(archive.read_bytes()).hexdigest()
 if actual!=EXPECTED:raise ValueError(f'Archive hash mismatch: {actual}')
 with tarfile.open(archive) as t:t.extractall(target,filter='data')
 print(target/'stockfish/stockfish-macos-m1-apple-silicon')
if __name__=='__main__':main()
