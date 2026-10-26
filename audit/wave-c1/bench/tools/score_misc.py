import json,re,os,sys
B=os.environ['B']
def text(p):
    r=''
    for l in open(p):
        try:o=json.loads(l)
        except: continue
        if o.get('type')=='result': r=o.get('result','')
    return r
ANIM={'A1 transition:all on backdrop':r'transition:\s*all|transition: all|\ball\b.*transition|transition.*\ball\b',
 'A2 animates layout props (top/width/height)':r'width|height|\btop\b',
 'A3 scale(0) entrance':r'scale\(0\)|scale\(0\.|from 0|starts? at (zero|0)',
 'A4 ease-in on UI entrance':r'ease-in',
 'A5 linear for movement':r'linear',
 'A6 durations too long (0.9/1.2/2s)':r'1\.2s|0\.9s|too long|duration',
 'A7 infinite animation/margin keyframes':r'infinite|margin',
 'A8 no prefers-reduced-motion':r'reduced-motion|reduced motion',
 'A9 rAF setState each frame (re-render)':r'requestanimationframe|raf|setstate|re-render|rerender',
 'A10 will-change overuse':r'will-change',
 'A11 :active scale(0.5) too extreme':r'scale\(0\.5\)|0\.5|active',
 'A12 expensive hover shadow transition':r'box-shadow|shadow'}
AUD={'U1 no viewport meta':r'viewport','U2 no lang':r'\blang\b','U3 no h1/landmarks/semantics':r'landmark|<h1|<main|<nav|heading',
 'U4 div onclick not buttons/keyboard':r'onclick|keyboard|<button|role=','U5 img no alt':r'\balt\b','U6 input no label':r'label',
 'U7 outline:none/no focus style':r'outline|focus','U8 low contrast':r'contrast','U9 fixed 1200px/not responsive':r'1200|responsive|fixed.?width|horizontal scroll|overflow',
 'U10 tiny fonts':r'font-size|11px|10px|12px|13px|small text|tiny','U11 faq not accessible (aria-expanded)':r'aria-expanded|disclosure|<details|faq|accordion','U12 placeholder-only/autocomplete/type=email':r'type=.?email|autocomplete|placeholder'}
for name,D,arms,pre in (('ANIM',ANIM,['base','ra','ap'],'anim'),('AUDIT',AUD,['base','wdg'],'audit')):
    T={a:text(f'{B}/out/{pre}__{a}.jsonl').lower() for a in arms}
    print(name,'defect'.ljust(42),*[a.ljust(6) for a in arms]); tot={a:0 for a in arms}
    for k,p in D.items():
        row=[]
        for a in arms:
            h=bool(re.search(p,T[a])); tot[a]+=h; row.append(('Y' if h else '-').ljust(6))
        print('    ',k.ljust(42),*row)
    print('    TOTAL'.ljust(47),*[str(tot[a]).ljust(6) for a in arms]); print('    words'.ljust(47),*[str(len(T[a].split())).ljust(6) for a in arms])
