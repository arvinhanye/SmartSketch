#!/usr/bin/env python3
"""Package precompiled launchers. Never build/publish images or read local .env."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]
TARGETS=('darwin-arm64','darwin-amd64','windows-amd64')

def _manifest(path):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate manifest field')
            out[k]=v
        return out
    data=json.loads(path.read_bytes(),object_pairs_hook=pairs)
    if set(data)!={'version','backend_image','frontend_image','neo4j_image','compose_sha256','targets'}:raise ValueError('manifest fields')
    if not isinstance(data['version'],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,64}',data['version']) or sorted(data['targets'])!=sorted(TARGETS):raise ValueError('manifest version or targets')
    for field,prefix in [('backend_image','ghcr.io/arvinhanye/smartsketch-backend@sha256:'),('frontend_image','ghcr.io/arvinhanye/smartsketch-frontend@sha256:'),('neo4j_image','neo4j@sha256:')]:
        if not isinstance(data[field],str) or not re.fullmatch(re.escape(prefix)+r'[a-f0-9]{64}',data[field]):raise ValueError('immutable image required')
    if data['compose_sha256']!=hashlib.sha256((ROOT/'packaging/compose.release.yaml').read_bytes()).hexdigest():raise ValueError('Compose checksum mismatch')
    return data

def package_release(manifest_path,binaries_dir,output_dir):
    manifest_path=Path(manifest_path);binaries_dir=Path(binaries_dir);output_dir=Path(output_dir)
    data=_manifest(manifest_path)
    sources={target:binaries_dir/('smartsketch-launcher-'+target+('.exe' if target.startswith('windows') else '')) for target in TARGETS}
    if any(not p.is_file() or p.is_symlink() or p.stat().st_size==0 for p in sources.values()):raise ValueError('precompiled launchers missing')
    if output_dir.exists():raise ValueError('output must be a new directory')
    output_dir.mkdir(parents=True,mode=0o700);outputs=[]
    for target in TARGETS:
        name='SmartSketch-'+data['version']+'-'+target
        with tempfile.TemporaryDirectory(prefix='smartsketch-package-') as temp:
            bundle=Path(temp)/name;(bundle/'bin').mkdir(parents=True)
            files={'release-manifest.json':manifest_path.read_bytes(),'compose.release.yaml':(ROOT/'packaging/compose.release.yaml').read_bytes(),'README.md':(ROOT/'docs/startup-guide.md').read_bytes(),'target.txt':(target+'\n').encode()}
            entry='start-windows.cmd' if target.startswith('windows') else 'start-macos.command'
            files[entry]=(ROOT/'packaging'/entry).read_bytes()
            for relative,body in files.items():(bundle/relative).write_bytes(body)
            binary=bundle/'bin'/('smartsketch-launcher.exe' if target.startswith('windows') else 'smartsketch-launcher');binary.write_bytes(sources[target].read_bytes());os.chmod(binary,0o755);os.chmod(bundle/entry,0o755)
            output=output_dir/(name+('.zip' if target.startswith('windows') else '.tar.gz'))
            if target.startswith('windows'):
                with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                    for path in sorted(bundle.rglob('*')):
                        if path.is_file():archive.write(path,path.relative_to(bundle.parent).as_posix())
            else:
                with tarfile.open(output,'w:gz') as archive:archive.add(bundle,arcname=name)
            outputs.append(output)
    (output_dir/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in outputs))
    return outputs
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--binaries',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:package_release(args.manifest,args.binaries,args.output)
    except (ValueError,OSError,TypeError):parser.exit(1,'Release inputs failed validation; nothing was published.\n')
