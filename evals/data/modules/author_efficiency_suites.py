"""Authors the R3.5 efficiency fixtures (dev + holdout) for ToolPruner, ContextGate and WakeGate. Refuses to overwrite.

Independence caveat (stated, not hidden): written by the same model-assisted session that reviewed the earlier modules, from general
knowledge of real tool output, NOT from a human or from real logs of this machine. Essential strings are explicit substrings fixed
HERE, before any implementation change. DEV is for tuning; HOLDOUT is measured once before and once after the change and never tuned on.
Run: uv run python evals/data/modules/author_efficiency_suites.py
"""
import random
from pathlib import Path

import yaml

OUT = Path(__file__).parent


def noise(rng, kind, n):
    pools = {
        "build": ["[{i:>3}/412] Building object {h}", "  CC  obj/{h}.o", "  LD  lib{h}.a", "[info] resolving unit {h} ({i} of 412)"],
        "docker": ["#{i} [stage-2 {i}/9] layer {h} done", "#{i} sha256:{h}{h} {i}.{i}MB / 88.4MB", " ---> Using cache {h}", "Step {i}/31 : COPY layer{h} /opt/layer{h}"],
        "k8s": ["  Normal  Pulled     {i}m   kubelet  Container image already present on machine", "  Normal  Created    {i}m   kubelet  Created container sidecar-{h}",
                "  Normal  Started    {i}m   kubelet  Started container sidecar-{h}", "  Tolerations: node.kubernetes.io/not-ready op=Exists for 300s"],
        "net": ["* Added {h} to connection cache", "> User-Agent: probe/{i}", "< x-request-id: {h}{h}", "* TLSv1.3 (IN), TLS handshake, record {i}"],
        "test": ["ok {i} - case {h}", "    ... {h} {i} assertions evaluated", "# subtest {h} in {i}ms", "ok {i} - fixture {h} loaded"],
        "pkg": ["Collecting wheel-{h}", "  Downloading wheel_{h}-1.{i}.0-py3-none-any.whl (41 kB)", "  Preparing metadata (pyproject.toml): finished with status 'done'", "Requirement already satisfied: lib{h} in site-packages ({i}.0)"],
        "db": ["{i} rows migrated in batch {h}", "batch {h}: committed after {i} ms", "checkpoint {i} written ({h})", "vacuum pass {i}: {h} pages scanned"],
    }
    pool = pools[kind]
    return [rng.choice(pool).format(i=rng.randint(2, 411), h="%06x" % rng.randrange(1 << 24)) for _ in range(n)]


def out(rng, kind, head, before, ess_lines, after, tail, n1=90, n2=70):
    lines = head + noise(rng, kind, n1) + before + ess_lines + noise(rng, kind, n2) + after + tail
    return "\n".join(lines) + "\n"


def pruner(split):
    r = random.Random(7 if split == "dev" else 11)
    O = []
    def add(id, lang, goal, kind, head, ess, tail, before=(), after=(), n1=90, n2=70, extra=()):
        O.append({"id": f"tp2-{split}-{len(O) + 1:03d}", "lang": lang, "goal": goal,
                  "output": out(r, kind, list(head), list(before), list(ess), list(after), list(tail), n1, n2),
                  "essential": list(ess) + list(extra)})
    if split == "dev":
        add("", "en", "Why did the health check fail", "net", ["* Trying 10.8.0.12:8443...", "* Connected to svc.internal (10.8.0.12) port 8443"],
            ["< HTTP/1.1 503 Service Unavailable"], ["* Connection #0 to host svc.internal left intact", "curl exit"], )
        add("", "en", "Find the link failure", "build", ["cmake --build . -j8"], ["ld: symbol(s) not found for architecture arm64"], ["make finished", "see log"])
        add("", "en", "Why did the image build stop", "docker", ["Sending build context to Docker daemon  18.2MB"], ["/bin/sh: line 1:    77 Killed                  npm run build"], ["layer cleanup", "build aborted"])
        add("", "en", "Which test is failing", "test", ["TAP version 13", "1..40"], ["not ok 14 - handles empty payload"], ["# tests 40", "# pass 39"])
        add("", "tr", "Sertifika sorununu bul", "net", ["* Trying 192.168.1.20:443..."], ["x509: certificate signed by unknown authority"], ["* closing connection 0", "bitti"])
        add("", "en", "What stopped the backup", "db", ["backup job started"], ["ENOSPC: no space left on device, write"], ["job cleanup", "backup aborted"])
        add("", "en", "Why can't the dependency install", "pkg", ["pip install -r reqs.txt"], ["Could not find a version that satisfies the requirement torchx==9.9"], ["pip finished with problems", "done"])
        add("", "en", "Why did the pod restart", "k8s", ["Name: api-7d9f", "Namespace: prod"], ["    Last State:     Terminated", "      Reason:       OOMKilled", "      Exit Code:    137"],
            ["Events: <none>", "end of describe"], extra=[])
        add("", "en", "Is the branch behind", "build", ["git status"], ["have diverged, and have 3 and 5 different commits each, respectively."], ["nothing to commit", "clean"])
        add("", "tr", "Kaç test koştu", "test", ["test koşumu başladı"], ["Ran 812 tests in 41.2s"], ["süreç tamamlandı", "temizlik"])
    else:
        add("", "en", "Why is the API call rejected", "net", ["* Trying 10.8.0.30:443..."], ["< HTTP/2 429 "], ["* Connection #0 left intact", "done"])
        add("", "en", "Why did the tool die", "build", ["./render --scene big"], ["Segmentation fault (core dumped)"], ["wrapper: exiting", "see core"])
        add("", "en", "What is wrong with the deployment", "k8s", ["Name: worker-5c8"], ["worker-5c8   0/1   CrashLoopBackOff   14   31m"], ["describe complete", "no further events"])
        add("", "en", "Why did the sync stop", "net", ["rsync -a src/ remote:"], ["rsync: connection unexpectedly closed: Connection reset by peer"], ["sync aborted", "exit"])
        add("", "en", "Why can't the service reach the DB", "db", ["pool starting"], ["connect ECONNREFUSED 127.0.0.1:5432"], ["pool degraded", "retry later"])
        add("", "en", "Why does the HTTPS fetch fail", "net", ["python fetch.py"], ["ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"], ["fetch finished", "exit 1 reported above"])
        add("", "en", "Why did the batch crash", "db", ["batch runner v2"], ["Cannot allocate memory"], ["runner exit", "memory report skipped"])
        add("", "en", "What changed with python", "pkg", ["pip install pandas"], ["DeprecationWarning: pkg_resources is deprecated as an API"], ["finished", "cache updated"])
        add("", "en", "Which package versions got installed", "pkg", ["pip install -U data stack"], ["Successfully installed numpy-1.26.4 pandas-2.2.1 pyarrow-15.0.2"],
            ["cleaning temp", "removing cache", "finished metadata sync", "ok"])
        add("", "tr", "Hangi imzayla çıktı", "pkg", ["görüntü yayınlandı"], ["Digest: sha256:9aa17c3be0"], ["etiket yazıldı", "temizlik", "bitti", "son"])
        add("", "en", "Why did the worker exit", "build", ["worker 3 started"], ["Process exited with signal SIGSEGV"], ["supervisor: restarting", "done"])
        add("", "en", "What is the service state", "db", ['{"service":"ledger","state":"ok"}'], ['{"service":"ledger","status":"degraded","lag_ms":4200}'], ['{"service":"ledger","state":"ok"}', "end", "done", "idle"])
        add("", "tr", "Neden bağlanamadı", "net", ["bağlantı deneniyor"], ["connect: network is unreachable"], ["yeniden deneme yok", "çıkış", "bitti"])
        add("", "en", "Why did the mount fail", "build", ["mount -t nfs share /mnt"], ["mount.nfs: Operation not permitted"], ["mount aborted", "bye"])
    return {"version": 1, "suite": f"toolpruner-suite-v2-{split}", "authored": "2026-10-16", "provenance": __doc__.split("\n")[2][:200],
            "metric": "essential string retained verbatim in the pruned view; exact recovery from the stored original", "outputs": O}


def contextgate(split):
    r = random.Random(21 if split == "dev" else 33)
    T = []
    def add(lang, constraint, results, essential):
        items = [{"id": "u1", "role": "user", "kind": "text", "text": constraint}]
        for k, (tool, body) in enumerate(results):
            items += [{"id": f"c{k}", "role": "assistant", "kind": "tool_call", "text": f"run {tool}"},
                      {"id": f"r{k}", "role": "tool", "kind": "tool_result", "tool": tool, "text": body}]
        for k in range(7):
            items += [{"id": f"p{k}", "role": "assistant", "kind": "tool_call", "text": "check"},
                      {"id": f"q{k}", "role": "tool", "kind": "tool_result", "tool": "check", "text": "ok"}]
        items.append({"id": "u2", "role": "user", "kind": "text", "text": "Summarise what we found."})
        T.append({"id": f"cg2-{split}-{len(T) + 1:03d}", "lang": lang, "items": items, "essential": essential, "note": ""})
    def body(kind, ess, n1=60, n2=45):
        return "\n".join(noise(r, kind, n1) + ess + noise(r, kind, n2) + ["finished step", "next", "idle"]) + "\n"
    if split == "dev":
        add("en", "Do not touch the billing tables.", [("sql", body("db", ["Created resource id=88213 in region eu-west-1"]))], ["id=88213"])
        add("en", "Keep the cache TTL unchanged.", [("kubectl", body("k8s", ["    Reason:       OOMKilled", "    Exit Code:    137"]))], ["OOMKilled", "Exit Code:    137"])
        add("tr", "Üretim ortamına dokunma.", [("curl", body("net", ["< HTTP/1.1 503 Service Unavailable"]))], ["HTTP/1.1 503"])
        add("en", "Pin to the reviewed release.", [("git", body("build", ["revision 4421-b is the reviewed release"]))], ["revision 4421-b"])
        add("en", "Report the ticket reference.", [("jira", body("db", ["linked to ticket PAY-2291 by the importer"]))], ["PAY-2291"])
        add("en", "Only use the private registry.", [("docker", body("docker", ["x509: certificate signed by unknown authority"]))], ["x509: certificate signed by unknown authority"])
    else:
        add("en", "Do not rotate the keys.", [("psql", body("db", ["listening on port 5433 (replica)"]))], ["port 5433"])
        add("en", "Keep the schema frozen.", [("git", body("build", ["introduced in commit 9fceb02a by the importer"]))], ["9fceb02a"])
        add("tr", "Sürümü değiştirme.", [("pip", body("pkg", ["Successfully installed numpy-1.26.4 pandas-2.2.1"]))], ["numpy-1.26.4", "pandas-2.2.1"])
        add("en", "No restarts during business hours.", [("kubectl", body("k8s", ["worker-5c8   0/1   CrashLoopBackOff   14   31m"]))], ["CrashLoopBackOff"])
        add("en", "Leave the firewall as is.", [("curl", body("net", ["< HTTP/2 429 "]))], ["HTTP/2 429"])
        add("en", "Use the staging database only.", [("app", body("db", ["connect ECONNREFUSED 127.0.0.1:5432"]))], ["ECONNREFUSED 127.0.0.1:5432"])
        add("en", "Report latency exactly.", [("probe", body("net", ['{"p99_ms":4200,"region":"eu-1"}'] ))], ["p99_ms"])
        add("en", "Quote the exact segfault line.", [("render", body("build", ["Segmentation fault (core dumped)"]))], ["Segmentation fault (core dumped)"])
    return {"version": 1, "suite": f"contextgate-suite-v2-{split}", "authored": "2026-10-16", "provenance": __doc__.split("\n")[2][:200],
            "metric": "essential string present in the compacted view; exact recovery from the store", "transcripts": T}


def wakegate(split):
    C = []
    def c(lang, waiting, ev, gold, family, prev=None, skipped=0):
        C.append({"id": f"wg2-{split}-{len(C) + 1:03d}", "lang": lang, "family": family, "waiting_for": waiting, "event": ev,
                  "previous_observation": prev, "skipped": skipped, "gold": gold})
    PR, PRT = "Code review comments on pull request 482", "482 numaralı çekme isteğine inceleme yorumları"
    CI, CIT = "The nightly integration run to finish", "Gece entegrasyon çalışmasının bitmesi"
    HR = "A reply from HR about the interview"
    if split == "dev":
        c("en", CI, {"kind": "alert", "summary": "TLS certificate for api.example.com has expired", "source": "monitor"}, "must_wake", "expired")
        c("en", CI, {"kind": "alert", "summary": "Deploy key was revoked and pushes are now denied", "source": "git"}, "must_wake", "denied")
        c("en", PR, {"kind": "alert", "summary": "Database connection refused from the worker pool", "source": "monitor"}, "must_wake", "refused")
        c("tr", CIT, {"kind": "alert", "summary": "Hizmet erişilemiyor, sağlık kontrolü yanıt vermiyor", "source": "izleme"}, "must_wake", "unreachable")
        c("en", PR, {"kind": "email", "summary": "Your invoice is overdue and the account will be suspended", "source": "billing"}, "must_wake", "overdue")
        c("en", HR, {"kind": "email", "summary": "Weekly digest: 5 lessons learned from failure in startups. Unsubscribe", "source": "newsletter@blog.example"}, "should_defer", "bulk_failure_word")
        c("en", HR, {"kind": "email", "summary": "Newsletter: prices are down this week! Unsubscribe", "source": "promo@shop.example"}, "should_defer", "bulk_down_word")
        c("tr", PRT, {"kind": "email", "summary": "Bülten: bu haftanın hata ayıklama ipuçları. Abonelikten çık", "source": "bulten@ornek.com"}, "should_defer", "bulk_tr")
        c("en", HR, {"kind": "email", "summary": "Re: second round interview times for Thursday", "source": "dana@acme.com"}, "wake_ok", "relevant")
        c("en", PR, {"kind": "email", "summary": "New review comments on PR 482", "source": "github"}, "wake_ok", "relevant")
        c("en", CI, {"kind": "timer", "observation": {"status": "running", "done": 41}}, "should_defer", "no_change", prev={"status": "running", "done": 41})
        c("en", CI, {"kind": "webhook", "summary": "Nightly run finished: 812 passed", "source": "ci"}, "wake_ok", "relevant")
    else:
        c("en", PR, {"kind": "alert", "summary": "Service certificate expires in 2 hours and was not renewed", "source": "monitor"}, "must_wake", "expired")
        c("en", CI, {"kind": "alert", "summary": "Access to the artifact bucket was forbidden (403)", "source": "storage"}, "must_wake", "denied")
        c("en", PR, {"kind": "alert", "summary": "Queue consumer rejected the batch and dropped 40 messages", "source": "queue"}, "must_wake", "rejected")
        c("tr", CIT, {"kind": "alert", "summary": "Veritabanı bağlantısı reddedildi", "source": "izleme"}, "must_wake", "refused_tr")
        c("tr", PRT, {"kind": "alert", "summary": "Sertifikanın süresi doldu", "source": "izleme"}, "must_wake", "expired_tr")
        c("en", HR, {"kind": "email", "summary": "Your subscription payment is overdue; service will be locked", "source": "billing@vendor.example"}, "must_wake", "overdue")
        c("en", CI, {"kind": "alert", "summary": "Primary node is unreachable from two regions", "source": "monitor"}, "must_wake", "unreachable")
        c("en", PR, {"kind": "alert", "summary": "Job was OOM killed on the build agent", "source": "ci"}, "must_wake", "killed")
        c("en", HR, {"kind": "email", "summary": "Newsletter: how teams recover from failure. Unsubscribe", "source": "newsletter@mag.example"}, "should_defer", "bulk_failure_word")
        c("en", HR, {"kind": "email", "summary": "Promo digest: flights down 40 percent. Unsubscribe here", "source": "deals@travel.example"}, "should_defer", "bulk_down_word")
        c("tr", HR, {"kind": "email", "summary": "Haftalık bülten: hata yönetimi üzerine yazılar. Abonelikten çık", "source": "bulten@ornek.com"}, "should_defer", "bulk_tr")
        c("en", HR, {"kind": "email", "summary": "Digest: security habits for remote teams. Unsubscribe", "source": "digest@sec.example"}, "should_defer", "bulk_security_word")
        c("en", PR, {"kind": "email", "summary": "Newsletter: reviewing pull requests faster. Unsubscribe", "source": "newsletter@dev.example"}, "should_defer", "bulk_overlap_topic")
        c("en", HR, {"kind": "email", "summary": "Re: interview schedule, can you do Friday?", "source": "dana@acme.com"}, "wake_ok", "relevant")
        c("en", CI, {"kind": "timer", "observation": {"status": "running", "done": 7}}, "should_defer", "no_change", prev={"status": "running", "done": 7})
        c("en", PR, {"kind": "email", "summary": "Newsletter: unsubscribe confirmation required for your PR notifications - please approve", "source": "noreply@github.example", "requires_approval": True}, "must_wake", "bulk_but_approval")
    return {"version": 1, "suite": f"wakegate-suite-v2-{split}", "authored": "2026-10-16", "provenance": __doc__.split("\n")[2][:200], "cases": C}


for split in ("dev", "holdout"):
    for name, fn in (("toolpruner", pruner), ("contextgate", contextgate), ("wakegate", wakegate)):
        p = OUT / f"{name}-suite-v2-{split}.yaml"
        if p.exists():
            raise RuntimeError(f"refusing to overwrite {p}")
        p.write_text(yaml.safe_dump(fn(split), sort_keys=False, allow_unicode=True))
        print("wrote", p.name)
