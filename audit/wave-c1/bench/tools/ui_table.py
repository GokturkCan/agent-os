import json,sys,os
B=os.environ['B']
keys=['overflowX','contrastFail','contrastUnknown','contrastChecked','worst','small24','fakeButtons','imgNoAlt','inputNoLabel','noFocusStyle','h1','landmarks','fontMin']
print('arm | bytes | missing | ext | rm(anim) | w:overflow | contrastFail/checked(unk) worst | small24 | fakeBtn | imgNoAlt | noLabel | noFocus | lang vp h1 landm | fontMin')
for a in sys.argv[1:]:
    p=f'{B}/out/ui_{a}.json'
    try: r=json.load(open(p))
    except Exception as e: print(a,'ERR',e); continue
    W=r['widths']; m4=W['390']; m1=W['1440']
    ov='/'.join(str(W[w]['overflowX']) for w in ('390','768','1440'))
    print(f"{a} | {r['bytes']} | {r['missing']} | ext={r['external']} | rm={r['reducedMotion']}(anim={r['hasAnimation']}) | ov {ov} | {m1['contrastFail']}/{m1['contrastChecked']}(unk {m1['contrastUnknown']}) worst {m1['worst']} (390: {m4['contrastFail']}/{m4['contrastChecked']}) | s24 {m4['small24']} | fake {m1['fakeButtons']} | alt {m1['imgNoAlt']} | lbl {m1['inputNoLabel']} | nofocus {m1['noFocusStyle']}/{m1['interactive']} | lang={m1['lang']} vp={m1['viewportMeta']} h1={m1['h1']} lm={m1['landmarks']} | font {m1['fontMin']}/{m4['fontMin']}")
