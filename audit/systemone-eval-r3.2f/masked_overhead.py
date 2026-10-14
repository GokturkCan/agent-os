"""Separates lookski/openjev method overhead (prompt build + tokenize + mask/softmax + render) from the
Qwen3-0.6B forward pass. Run with state/runtime/openjev-masked/venv/bin/python <snapshot_dir>. Offline."""
import json, os, statistics as st, sys, time
os.environ["HF_HUB_OFFLINE"] = "1"
import torch
from openjev.core import LocalJev, _build_prompt
from openjev.types import Choice
e = LocalJev(model_id=sys.argv[1], device="mps", dtype="bfloat16")
tok, rows = e.tokenizer, []
for i in range(210):
    n = 2 + i % 4
    q = Choice(instructions="Which worker should handle this task?",
               criteria={f"w{k}": f"roles: coding, review; access: local; cost: free; latency: fast #{k}" for k in range(n)})
    state = json.dumps({"task_class": "coding", "stage": "fastgate", "attempt": 1 + i % 3})
    t0 = time.perf_counter(); prompt = _build_prompt(tok, state, q, e.system_prompt)
    inputs = tok(prompt, return_tensors="pt", add_special_tokens=False).to(e.device); t1 = time.perf_counter()
    with torch.no_grad(): e.model(**inputs, logits_to_keep=1)[0] if False else e.model(**inputs, logits_to_keep=1)
    torch.mps.synchronize(); t2 = time.perf_counter()
    e.answer_one(q, state); t3 = time.perf_counter()          # whole method end to end
    rows.append((t1 - t0, t2 - t1, t3 - t2, int(inputs["input_ids"].shape[1])))
rows = rows[10:]
f = lambda k: round(st.median(r[k] for r in rows) * 1000, 2)
print(json.dumps({"n": len(rows), "median_ms": {"prompt_build_and_tokenize": f(0), "model_forward_only": f(1),
      "full_method_answer_one": f(2)}, "median_input_tokens": st.median(r[3] for r in rows),
      "note": "method overhead = full_method - model_forward (includes its own prompt build, mask, softmax, render)"}))
