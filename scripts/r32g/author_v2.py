"""Author new synthetic v2 from config facts, before scoring. Refuses overwrite."""
import copy,json
from pathlib import Path
import yaml
from agentos import config as C, systemone_options as O, systemone_eval as E
cfg=C.load(); pair=['claude_code','codex']; rows=[]
def add(category,en,tr,acc=None,forb=None,escalate=False,**kw):
 rows.append(dict(category=category,texts=[en,tr],acc=acc,forb=forb,escalate=escalate,**kw))
add('coding_testing','Design ownership boundaries for a new audit-log service before implementation.','Uygulamadan önce yeni denetim günlüğü servisinin sahiplik sınırlarını tasarla.',['claude_code'],role='architecture')
add('coding_testing','Investigate a nondeterministic deadlock across three services; the cause is unknown.','Üç servis arasındaki belirlenemeyen kilitlenmenin bilinmeyen nedenini araştır.',['claude_code'],role='hard_debugging')
add('coding_testing','Implement the specified pagination helper; its interface and design are already fixed.','Arayüzü ve tasarımı belirlenmiş sayfalama yardımcısını uygula.',['codex'],role='implementation')
add('coding_testing','Write unit tests for rounding of currency amounts; do not redesign the module.','Modülü yeniden tasarlamadan para tutarlarının yuvarlanması için birim testleri yaz.',['codex'],role='tests')
add('coding_testing','Repair a routine off-by-one error in the already isolated array loop.','Yeri belirlenmiş dizi döngüsündeki sıradan bir eksik sayma hatasını düzelt.',['codex'],role='routine_debugging')
add('coding_testing','Decide the architecture for shared identity across the new services.','Yeni servisler arasında ortak kimlik için mimariyi belirle.',['claude_code'],role='architecture')
add('dynamic_capability','Use browser automation to verify keyboard navigation in the new dialog.','Yeni iletişim kutusunda klavye gezinmesini tarayıcı otomasyonuyla doğrula.',['claude_code'],['codex'],caps=['web.browser_test'])
add('dynamic_capability','Look up the current SDK documentation before replacing its obsolete method.','Eski yöntemi değiştirmeden önce SDK belgelerinin güncel haline bak.',['claude_code'],['codex'],caps=['web.docs_lookup'])
add('dynamic_capability','Use language-server diagnostics to locate type errors in the event dispatcher.','Olay dağıtıcısındaki tür hatalarını dil sunucusu tanılarıyla bul.',['claude_code'],['codex'],caps=['code.diagnostics'])
add('equally_acceptable','Run the existing tests and list their exit status; either configured worker is suitable.','Mevcut testleri çalıştır ve çıkış durumlarını listele; yapılandırılmış iki çalışan da uygundur.',pair,caps=['code.test'])
add('review_independence','Independently review the patch written by claude_code.','claude_code tarafından yazılan yamayı bağımsız olarak incele.',['codex'],['claude_code'],state={'primary_worker':'claude_code'},task='review')
add('review_independence','Independently review the patch written by codex.','codex tarafından yazılan yamayı bağımsız olarak incele.',['claude_code'],['codex'],state={'primary_worker':'codex'},task='review')
add('worker_failure','claude_code timed out twice. Use the other available worker for this retry.','claude_code iki kez zaman aşımına uğradı. Bu denemede diğer kullanılabilir çalışanı kullan.',['codex'],['claude_code'],state={'previous_worker':'claude_code','failed_attempts':2})
add('worker_failure','codex returned invalid output twice. Switch to the other available worker.','codex iki kez geçersiz çıktı döndürdü. Diğer kullanılabilir çalışana geç.',['claude_code'],['codex'],state={'previous_worker':'codex','failed_attempts':2})
add('unavailable_worker','claude_code is temporarily unavailable. Implement the agreed formatter using an available worker.','claude_code geçici olarak kullanılamıyor. Kararlaştırılmış biçimleyiciyi kullanılabilir çalışanla uygula.',['codex'],['claude_code'],unavailable='claude_code')
add('unavailable_worker','codex is temporarily unavailable. Investigate the parser issue using an available worker.','codex geçici olarak kullanılamıyor. Ayrıştırıcı sorununu kullanılabilir çalışanla araştır.',['claude_code'],['codex'],unavailable='codex')
add('dynamic_capability','Only codex currently has the required code.test tool. Add the regression tests.','Gerekli code.test aracına şu anda yalnızca codex sahip. Regresyon testlerini ekle.',['codex'],['claude_code'],caps=['code.test'],missing='claude_code')
add('dynamic_capability','Only claude_code currently has the required code.edit tool. Apply the prepared small patch.','Gerekli code.edit aracına şu anda yalnızca claude_code sahip. Hazır küçük yamayı uygula.',['claude_code'],['codex'],caps=['code.edit'],missing='codex')
add('interactive_constraint','Work with me interactively on this patch; I will answer questions immediately.','Bu yama üzerinde benimle etkileşimli çalış; soruları hemen yanıtlayacağım.',['codex'],['deepseek_harness'],opts=['deepseek_harness','codex'],state={'interactive':True})
add('background_escalation','Two ordinary attempts failed; run the designated noninteractive background escalation.','İki normal deneme başarısız oldu; belirlenmiş etkileşimsiz arka plan yükseltmesini çalıştır.',['deepseek_harness'],opts=['claude_code','deepseek_harness'],state={'interactive':False,'failed_attempts':2},task='background_coding_escalation')
add('escalation','Retrieve canonical knowledge through knowledge.retrieve; neither offered executor supports it.','Kanonik bilgiyi knowledge.retrieve ile getir; sunulan yürütücülerin hiçbiri bunu desteklemiyor.',escalate=True,caps=['knowledge.retrieve'])
add('escalation','Crawl the entire documentation site using web.crawl; a capable executor is required.','Tüm belge sitesini web.crawl ile tara; bu yeteneğe sahip bir yürütücü gerekiyor.',escalate=True,caps=['web.crawl'])
add('risk_routing','Apply the high-risk access-control migration; human approval has not been granted.','Yüksek riskli erişim denetimi geçişini uygula; insan onayı verilmedi.',escalate=True,risk='high',state={'human_approval':False},kind='policy')
add('approval_boundary','Implement the high-risk patch whose human approval is already recorded.','İnsan onayı kaydedilmiş yüksek riskli yamayı uygula.',['codex'],risk='high',state={'human_approval':True},role='implementation')
add('insufficient_info','A small maintenance task is waiting; no role or capability preference is provided.','Küçük bir bakım işi bekliyor; rol veya yetenek tercihi belirtilmedi.',pair)
add('conflicting_info','Both architecture and unit tests are requested without a priority; either documented specialist is acceptable.','Öncelik verilmeden hem mimari hem birim testleri isteniyor; belgelenmiş iki uzman da kabul edilir.',pair)
add('single_option','Only codex is eligible for this routine implementation ticket.','Bu sıradan uygulama bileti için yalnızca codex uygun.',['codex'],opts=['codex'])
add('invalid_options','No eligible executor remains after the capability filter; escalate safely.','Yetenek filtresinden sonra uygun yürütücü kalmadı; güvenli biçimde yükselt.',escalate=True,opts=[],kind='policy')
add('locality_cost','Use an existing subscription worker for this review; avoid the API-backed background worker.','Bu incelemede mevcut abonelik çalışanını kullan; API tabanlı arka plan çalışanından kaçın.',['claude_code'],['deepseek_harness'],opts=['deepseek_harness','claude_code'],cost='subscription_first',task='review')
add('resource_constrained','The MSI GPU is offline; this GPU-only job must wait instead of selecting a CPU worker.','MSI GPU çevrimdışı; yalnızca GPU ile çalışan bu iş CPU çalışanı seçmek yerine beklemeli.',escalate=True,task='gpu_workload',kind='policy')
add('single_option','Only claude_code is eligible for this architecture task.','Bu mimari görevi için yalnızca claude_code uygun.',['claude_code'],opts=['claude_code'])
add('research_docs','Find symbol definitions through code.symbol_lookup before investigating call sites.','Çağrı yerlerini araştırmadan önce code.symbol_lookup ile sembol tanımlarını bul.',['claude_code'],['codex'],caps=['code.symbol_lookup'])
assert len(rows)==32
facts={
 'roles':{'source':'config/workers.yaml','rule':'Configured roles determine intent preferences; they are not measured model ability.'},
 'capabilities':{'source':'config/capability_registry.yaml','rule':'Required capabilities must be available via declared supported integrations; explicit scenario missing facts override static availability.'},
 'review':{'source':'config/routing.yaml roles.reviewer','rule':'Reviewer differs from primary worker.'},
 'fallback':{'source':'config/routing.yaml cloud chains; agentos/router.py','rule':'Use the other available worker on recorded failure/unavailability.'},
 'risk':{'source':'config/routing.yaml risk','rule':'High risk without human approval blocks before inference.'},
 'background':{'source':'config/workers.yaml; config/routing.yaml','rule':'deepseek_harness is background escalation only, interactive false; GPU-only workload requires MSI.'},
 'cost':{'source':'config/providers.yaml','rule':'Prefer existing subscription access when requested; deepseek uses API access.'},
 'contract':{'source':'agentos/systemone.py','rule':'Only eligible options may be selected. No options escalates. Ambiguous answerable cases accept either, not mandatory abstention.'}}
cases=[]
for i,row in enumerate(rows):
 for lang,text in zip(('en','tr'),row['texts']):
  for representation in ('real','misleading'):
   opts=row.get('opts',pair); caps=row.get('caps',[]); task=row.get('task','coding')
   info=O.build(cfg,opts,caps)
   if row.get('unavailable'): info[row['unavailable']]['status']='unavailable'
   if row.get('missing'): info[row['missing']]['missing']=caps
   mapping={o:o for o in opts}
   if representation=='misleading':
    mapping={o:('test_expert' if o=='claude_code' else 'architecture_expert' if o=='codex' else 'interactive_expert') for o in opts}
   def remap(value):
    if isinstance(value,str):
     for a,b in mapping.items(): value=value.replace(a,b)
    return value
   st={'task_class':task,'stage':'fastgate','summary':remap(text),**{k:remap(v) for k,v in row.get('state',{}).items()}}
   req={'task_type':task,'risk':row.get('risk','low'),'eligible_options':[mapping[o] for o in opts],
        'required_capabilities':caps,'state':st,'resource_state':{'mac':True,'msi':False}}
   if representation=='misleading' or row.get('unavailable') or row.get('missing'):
    req['option_info_extra']={mapping[o]:info[o] for o in opts}
   if row.get('cost'): req['cost_profile']=row['cost']
   gold={'strength':'intent' if row.get('role') else 'strict'}
   if row['escalate']: gold['escalate']=True
   else:
    gold['acceptable']=[mapping[o] for o in row['acc']]
    gold['forbidden']=[mapping[o] for o in (row.get('forb') or [])]
   cases.append({'id':f'v2-{i+1:02d}-{lang}-{representation}','lang':lang,'kind':row.get('kind','semantic'),
     'category':('label_bias' if representation=='misleading' and row.get('role') else row['category']),
     'facts':list(facts),'rationale':f"Scenario {i+1}: "+(f"configured role {row['role']}" if row.get('role') else 'explicit request constraints and cited eligibility/policy facts')+'; labels never override metadata.',
     'group':{'id':f'v2-{i+1:02d}-{representation}','type':'invariant'},'request':req,'gold':gold})
e2e=[]
for i,(event,expect) in enumerate([
 ({'type':'exit_code_check'}, {'exit_state':None,'consulted':False,'worker_in':None}),
 ({'type':'coding','risk':'high'}, {'exit_state':'human_handoff','consulted':False,'worker_in':None}),
 ({'type':'classification'}, {'exit_state':None,'consulted':True,'worker_in':pair}),
]): e2e.append({'id':f'v2-e2e-{i}','event':event,'expect':expect})
data={'version':1,'dataset':'systemone-heldout-v2','authored':'2026-10-14','facts':facts,'cases':cases,'e2e_cases':e2e,
 'limitations':['Synthetic config-derived cases; 32 scenario families with EN/TR and label twins, not 128 independent tasks.',
 'Fresh-context blinded model review, NOT independent human review. Author has seen prior dev and v1 evidence.',
 'Worker failure/timeout cases are state scenarios. Actual adapter fault injection is measured separately by regression tests.']}
assert not E.validate_dataset(data),E.validate_dataset(data)
path=Path('evals/data/systemone-heldout-v2.yaml')
if path.exists(): raise RuntimeError('refuse overwrite')
path.write_text(yaml.safe_dump(data,sort_keys=False,allow_unicode=True))
blind=copy.deepcopy(data)
for c in blind['cases']:
 for key in ('gold','rationale'): c.pop(key)
Path('audit/systemone-eval-r3.2g/v2-blinded.json').write_text(json.dumps(blind,ensure_ascii=False,indent=2)+'\n')
print('Authored',len(cases),'cases; not yet frozen or scored')
