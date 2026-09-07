import io,json,re,subprocess,sys,tarfile,tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autodoc_py import generate
import argparse
parser=argparse.ArgumentParser(description='Audit every Vuer tag for source generation and API link integrity')
parser.add_argument('repo', help='Local Vuer Git clone with all tags')
parser.add_argument('--report', type=Path, required=True)
args=parser.parse_args()
repo=args.repo
def git(*args): return subprocess.check_output(['git','-C',repo,*args])
tags=git('tag','--sort=version:refname').decode().splitlines()
results=[]
for tag in tags:
    roots=git('ls-tree','--name-only',tag).decode().splitlines()
    candidates=[('src/vuer','vuer'),('vuer','vuer'),('tassa','tassa')]
    candidate=None
    for path,module in candidates:
        if path.split('/')[0] in roots and subprocess.run(['git','-C',repo,'cat-file','-e',f'{tag}:{path}'],capture_output=True).returncode==0:
            candidate=path,module;break
    if not candidate:
        results.append({'tag':tag,'status':'no package'});continue
    package,module=candidate
    with tempfile.TemporaryDirectory(prefix='autodoc-history-') as directory:
        root=Path(directory)
        archive=git('archive',tag,package)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith('.py'):
                    target=root/member.name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(tar.extractfile(member).read())
        output=root/'pages'
        try:
            count=generate(root/package,output,module)
            bad=[]
            for page in output.rglob('+Page.mdx'):
                for route,anchor in re.findall(r'\]\((/api[^#\s]*)#([^\s)]+)\)',page.read_text()):
                    target=output / route.removeprefix('/api').lstrip('/') / '+Page.mdx'
                    if not target.exists(): bad.append([str(page.relative_to(output)),route,'missing page'])
                    elif not any(re.sub(r'[^a-z0-9 _-]','',heading.lower()).replace(' ','-')==anchor for heading in re.findall(r'^## (.+)$',target.read_text(),re.M)):
                        bad.append([str(page.relative_to(output)),route,anchor,'missing anchor'])
            results.append({'tag':tag,'package':package,'pages':count,'status':'ok' if not bad else 'bad links','bad':bad})
        except Exception as error:
            results.append({'tag':tag,'package':package,'status':'error','error':str(error)})
    if len(results)%20==0: print(f'Checked {len(results)}/{len(tags)}',flush=True)
args.report.write_text(json.dumps(results,indent=2))
print(json.dumps({'total':len(results),'status_counts':{state:sum(r['status']==state for r in results) for state in set(r['status'] for r in results)},'failures':[r for r in results if r['status']!='ok']},indent=2))
