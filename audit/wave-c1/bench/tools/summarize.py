import sys, json, glob, os, collections
B=os.environ['B']
rows=[]
for p in sorted(glob.glob(B+'/out/*.jsonl')):
    name=os.path.basename(p)[:-6]
    tools=collections.Counter(); skills=[]; res=None; turns=0
    for l in open(p):
        try:o=json.loads(l)
        except: continue
        if o.get('type')=='assistant':
            for c in o['message'].get('content',[]):
                if c.get('type')=='tool_use':
                    tools[c['name']]+=1
                    if c['name']=='Skill': skills.append(c['input'].get('skill'))
        if o.get('type')=='result': res=o
    wall=open(p[:-6]+'.wall').read().strip() if os.path.exists(p[:-6]+'.wall') else '?'
    if not res: rows.append((name,'NO RESULT',wall)); continue
    u=res.get('usage',{})
    tot=(u.get('input_tokens',0)+u.get('cache_creation_input_tokens',0)+u.get('cache_read_input_tokens',0)+u.get('output_tokens',0))
    rows.append((name,f"cost=${res.get('total_cost_usd',0):.3f} turns={res.get('num_turns')} api_ms={res.get('duration_api_ms')} wall_s={wall} out_tok={u.get('output_tokens')} new_in={u.get('cache_creation_input_tokens',0)+u.get('input_tokens',0)} cached_in={u.get('cache_read_input_tokens',0)} denied={len(res.get('permission_denials',[]))} err={res.get('is_error')} skills={skills} tools={dict(tools)}"))
for r in rows: print(r[0],'|',r[1] if len(r)==2 else r[1])
