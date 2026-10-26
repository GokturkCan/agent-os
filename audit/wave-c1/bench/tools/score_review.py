import json,re,sys,os
B=os.environ['B']
D={ 'D1 deps omit query':[r'dependenc.*(query)|(query).*dependenc|\[endpoint\]'],
 'D2 race/no abort':[r'race|abort|out-of-order|out of order|stale response|cleanup'],
 'D3 swallowed error/loading':[r'swallow|empty catch|catch\s*\(\)|catch.*(error|loading)|r\.ok|res\.ok|response\.ok|never reset|stuck'],
 'D4 no URL encode':[r'encodeuricomponent|url-?encod|urlsearchparams|not encoded|unencoded'],
 'D5 push mutation':[r'push'],
 'D6 sort mutates':[r'\.sort|toSorted'],
 'D7 key=index':[r'key=\{i\}|index as (a )?key|key.*index|index.*key'],
 'D8 XSS':[r'xss|dangerouslysetinnerhtml|sanitiz'],
 'D9 stale closure':[r'stale closure|setsearches\(searches|functional update|searches \+ 1|searches\+1|prev =>|prev=>'],
 'D10 a11y':[r'keyboard|a11y|accessib|aria|<label|label'],
 'D11 unsafe cast':[r'as user|cast|type assertion|runtime validation|zod|unvalidated|unchecked']}
def text(p):
    r=None
    for l in open(p):
        try:o=json.loads(l)
        except: continue
        if o.get('type')=='result': r=o.get('result','')
    return r or ''
arms=sys.argv[1:]
print('defect'.ljust(28),*[a.ljust(7) for a in arms])
tot={a:0 for a in arms}; T={a:text(f'{B}/out/review__{a}.jsonl') for a in arms}
for k,pats in D.items():
    row=[]
    for a in arms:
        t=T[a].lower(); hit=any(re.search(p,t) for p in pats)
        if k.startswith('D5'): hit=hit and ('mutat' in t or 'setpicked' in t)
        if k.startswith('D6'): hit=hit and ('mutat' in t or 'in place' in t or 'copy' in t)
        tot[a]+=hit; row.append(('Y' if hit else '-').ljust(7))
    print(k.ljust(28),*row)
print('TOTAL'.ljust(28),*[str(tot[a]).ljust(7) for a in arms]); print('words'.ljust(28),*[str(len(T[a].split())).ljust(7) for a in arms])
