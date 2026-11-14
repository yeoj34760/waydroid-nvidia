#!/usr/bin/env python3
"""Generate exact-tag RM wire metadata from independent public C probe artifacts.
No driver loads, runtime probes, branch interpolation, or header guesses.
"""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
NATIVE=Path(__file__).resolve().parents[1]
SOURCES={}; layouts={}; versions={}; files=[]

def parse(path):
 raw=path.read_bytes(); files.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest()})
 sizes={}; fields={}; constants={}
 for line in raw.decode().splitlines():
  name,value=line.split('\t',1)
  if value.startswith('MISSING'):continue
  if value.startswith('size='):sizes[name]=int(value.split()[0][5:]);fields[name]=[]
  elif value.startswith('off='):
   parent,field=name.split('.',1)
   if parent in fields:fields[parent].append((field,int(value.split()[0][4:]),int(value.split()[1][4:])))
  elif value.startswith('0x'):constants[name]=int(value,16)
 nested={'nv_ioctl_card_info_t.pci_info':'nv_pci_info_t','nv_ioctl_nvos33_parameters_with_fd.params':'NVOS33_PARAMETERS'}
 for name,ff in fields.items():
  for field,off,length in ff:
   if field=='grRouteInfo':nested[name+'.'+field]='NV2080_CTRL_GR_ROUTE_INFO'
   if name=='NV_CHANNELGPFIFO_ALLOCATION_PARAMETERS' and field in ['instanceMem','userdMem','ramfcMem','mthdbufMem','errorNotifierMem','eccErrorNotifierMem']:
    nested[name+'.'+field]='NV_MEMORY_DESC_PARAMS'
 def flatten(name):
  out=[]
  for f,o,n in fields[name]:
   child=nested.get(name+'.'+f)
   if child and child in fields:
    out.extend((f+'.'+cf,o+co,cn) for cf,co,cn in flatten(child))
   else:out.append((f,o,n))
  return out
 shapes={name:(sizes[name],tuple(flatten(name))) for name in sizes}
 return shapes,constants

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--extend', nargs=2, metavar=('TAG', 'PROBE_DIRECTORY'),
                    help='extend the checked-in census with independently measured exact-release probes')
args=parser.parse_args()
if args.extend:
 # Preserve the checked-in census when the private historical probe archive is
 # unavailable. Only the new release comes from the supplied public C probes.
 source=(NATIVE/'src/compat_data.rs').read_text()
 measured={}
 for index,name,size,body in re.findall(r'static L(\d+): Layout = Layout \{ name: "(.*?)", size: (\d+), fields: &\[(.*?)\] };',source,re.S):
  ff=tuple((f,int(o),int(n)) for f,o,n in re.findall(r'Field \{ name: "(.*?)", offset: (\d+), len: (\d+) }',body))
  measured[index]=(name,(int(size),ff))
 profiles={}
 for index,ll,cc in re.findall(r'static P(\d+): Profile = Profile \{ layouts: &\[(.*?)\], constants: &\[(.*?)\] };',source,re.S):
  profiles[index]=({name:measured[i][1] for name,i in re.findall(r'\("(.*?)", &L(\d+)\)',ll)},
                   {name:int(value) for name,value in re.findall(r'\("(.*?)", (\d+)\)',cc)})
 for tag,index in re.findall(r'\("([0-9.]+)", &P(\d+)\)',source):
  versions[tag]=profiles[index]
 previous=json.loads((NATIVE/'tools/compat-provenance.json').read_text())
 assert len(versions)==previous['exact_tags'],'could not recover the complete checked-in tag census'
 assert len(profiles)==previous['profiles'],'could not recover the complete checked-in profiles'
 assert len(measured)==previous['layouts'],'could not recover the complete checked-in layouts'
 files.extend(previous['sources'])
else:
 paths={}
 for d in sorted((ROOT/'build/nv-km-archive/analysis/probe').iterdir()):
  p=d/'closed/probe-m64.tsv'
  if p.exists():paths.setdefault(d.name,[]).append(p)
 for d in sorted((ROOT/'build/rm-abi-stability/ranges/probe').iterdir()):
  p=d/'probe-m64.tsv'
  if p.exists():paths.setdefault(d.name,[]).append(p)
 for tag,pp in paths.items():
  result=None
  for p in pp:
   a=parse(p); b=parse(p.with_name('probe-m32.tsv'))
   assert a==b,(p,'wire m32/m64 mismatch')
   if result is not None:
    for index in [0,1]:
     assert all(result[index][k]==a[index][k] for k in set(result[index]) & set(a[index])),(tag,'closed/open overlapping public probe mismatch')
   result=a
  versions[tag]=result
 # Additional lifecycle contracts are independently compiled against each public
 # tag. Never fill missing old releases with another tag's layout.
 census=sorted(p.name for p in (ROOT/'build/rm-abi-stability/ranges/probe').iterdir() if (p/'probe-m64.tsv').exists())
 additional=[]
 for family in ['lifecycle','static-bar1','zcull','video','subcontext']:
  directories=sorted(p for p in (ROOT/'build/rm-abi-stability'/family).iterdir() if p.is_dir())
  assert [p.name for p in directories]==census,(family,'incomplete public tag census')
  additional.extend(directories)
 for directory in additional:
  tag=directory.name
  if tag not in versions:continue
  extra=parse(directory/'probe-m64.tsv')
  assert extra==parse(directory/'probe-m32.tsv'),(tag,directory.parent.name,'m32/m64 mismatch')
  original=versions[tag]
  for index in [0,1]:
   assert all(original[index][k]==extra[index][k] for k in set(original[index]) & set(extra[index])),(tag,directory.parent.name,'overlap mismatch')
  versions[tag]=tuple({**old,**new} for old,new in zip(original,extra))
  provenance=directory/'provenance.json'
  files.append({'path':str(provenance.relative_to(ROOT)),'sha256':hashlib.sha256(provenance.read_bytes()).hexdigest()})
# Complete release probes supplement the historical family-by-family archive.
releases=ROOT/'build/rm-abi-stability/releases'
additions=[(args.extend[0],Path(args.extend[1]).resolve())] if args.extend else [(p.name,p) for p in sorted(releases.glob('*')) if p.is_dir()]
for tag,directory in additions:
 proof=directory/'provenance.json'
 assert json.loads(proof.read_text())['tag']==tag,'probe provenance tag mismatch'
 result=parse(directory/'probe-m64.tsv')
 assert result==parse(directory/'probe-m32.tsv'),'wire m32/m64 mismatch'
 if tag in versions:assert versions[tag]==result,'existing exact release differs'
 versions[tag]=result
 files.append({'path':str(proof.relative_to(ROOT)),'sha256':hashlib.sha256(proof.read_bytes()).hexdigest()})
# Re-running the same measured addition is idempotent.
files=list({entry['path']:entry for entry in files}.values())
ref_shapes,ref_constants=versions['615.71.09']
# Keep all measured structures/constants, including DRM for callers' strict checks.
all_shapes=[];shape_ids={};profiles=[];profile_ids={};tags=[]
for tag,(shapes,consts) in sorted(versions.items()):
 entries=[]
 for name,(size,ff) in sorted(shapes.items()):
  k=(name,size,ff)
  if k not in shape_ids:shape_ids[k]=len(all_shapes);all_shapes.append(k)
  entries.append((name,shape_ids[k]))
 profile=(tuple(entries),tuple(sorted(consts.items())))
 if profile not in profile_ids:profile_ids[profile]=len(profiles);profiles.append(profile)
 tags.append((tag,profile_ids[profile]))
def q(x):return json.dumps(x)
lines=['// Generated by tools/generate-compat.py; exact C probe membership, no version inequalities.', '// m32 and m64 sizes/field offsets/constants cross-checked for every input.', 'use super::{Field, Layout, Profile};']
for i,(name,size,ff) in enumerate(all_shapes):
 lines.append(f'static L{i}: Layout = Layout {{ name: {q(name)}, size: {size}, fields: &[')
 lines.extend(f'Field {{ name: {q(f)}, offset: {o}, len: {n} }},' for f,o,n in ff)
 lines.append('] };')
for i,(entries,cc) in enumerate(profiles):
 lines.append(f'static P{i}: Profile = Profile {{ layouts: &[')
 lines.extend(f'({q(n)}, &L{s}),' for n,s in entries);lines.append('], constants: &[')
 lines.extend(f'({q(n)}, {v}),' for n,v in cc);lines.append('] };')
lines.append('pub(super) static VERSIONS: &[(&str, &Profile)] = &[')
lines.extend(f'({q(t)}, &P{i}),' for t,i in tags);lines.append('];')
lines.append('pub(super) static CANONICAL: &Profile = &P'+str(dict(tags)['615.71.09'])+';')
# Never silently drop a previously measured release when a local archive is incomplete.
existing_tags=set(re.findall(r'\("([0-9.]+)", &P\d+\)',(NATIVE/'src/compat_data.rs').read_text()))
assert existing_tags <= versions.keys(),('missing previously measured releases',sorted(existing_tags-versions.keys()))
(NATIVE/'src/compat_data.rs').write_text('\n'.join(lines)+'\n')
(NATIVE/'tools/compat-provenance.json').write_text(json.dumps({'sources':files,'exact_tags':len(tags),'profiles':len(profiles),'layouts':len(all_shapes),'authority':'Independent C public-header probes, m32/m64. No closed-core semantics inferred. No pre515 missing struct inferred.'},indent=1)+'\n')
print(len(tags),'exact tags;',len(profiles),'profiles;',len(all_shapes),'layouts;',len(files),'C probe files')
