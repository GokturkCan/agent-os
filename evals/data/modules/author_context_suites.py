"""Authors the ContextGate and tool-pruner acceptance suites (R3.2G) BEFORE any run. Deterministic (seeded) content.

Each transcript / tool output lists `essential`: exact strings that must survive in the compacted/pruned VIEW (a missing
one is a false drop). Content is synthetic and contains no real secrets (placeholders only).
Run: uv run python evals/data/modules/author_context_suites.py
"""
import json
import random
from pathlib import Path

import yaml

rng = random.Random(1337)


def npm_noise(n):
    pk = ["lodash", "react", "typescript", "eslint", "vite", "zod", "axios", "chalk", "commander", "dotenv"]
    out = []
    for i in range(n):
        p = rng.choice(pk)
        out.append(f"npm http fetch GET 200 https://registry.npmjs.org/{p} {rng.randint(5, 900)}ms (cache revalidated)")
    return out


def progress(n):
    return [f"Downloading layer {rng.randint(1000, 9999)}  [{'#' * (i % 20)}{'.' * (20 - i % 20)}] {i * 5 % 100}%" for i in range(n)]


def build_log(err_file, err_code, err_msg, n=120):
    lines = [f"[{i:04d}] compiling module_{rng.randint(1, 400)}.o ... ok" for i in range(n)]
    pos = n // 2
    lines.insert(pos, f"{err_file}:{rng.randint(10, 300)}:7: error {err_code}: {err_msg}")
    lines.append("make: *** [all] Error 2")
    lines.append("exit code 2")
    return "\n".join(lines)


def prose(topic, n):
    words = ("the system uses a layered design where each component handles one concern and passes data forward "
             "through well defined interfaces so that changes stay local and testing stays simple").split()
    return "\n".join(" ".join(rng.choice(words) for _ in range(14)) + "." for _ in range(n)) + f"\n(about {topic})"


def pytest_out(failing, path, n=150):
    lines = [f"tests/test_mod_{i % 30}.py::test_case_{i} PASSED" for i in range(n)]
    lines.insert(n - 10, f"{path}::{failing} FAILED")
    lines += ["=================================== FAILURES ===================================",
              f"___ {failing} ___", f"E       AssertionError: expected 42 == 41", f'  File "{path.split("::")[0]}", line 88, in {failing}',
              f"=========== 1 failed, {n - 1} passed in 12.31s ==========="]
    return "\n".join(lines)


# ------------------------------------------------------------ ContextGate transcripts
def T(id, lang, items, essential, goal_note=""):
    return {"id": id, "lang": lang, "items": items, "essential": essential, "note": goal_note}


def user(t):
    return {"role": "user", "kind": "text", "text": t}


def asst(t):
    return {"role": "assistant", "kind": "text", "text": t}


def call(tool, t):
    return {"role": "assistant", "kind": "tool_call", "tool": tool, "text": t}


def res(tool, t):
    return {"role": "tool", "kind": "tool_result", "tool": tool, "text": t}


filler_calls = lambda k: [x for i in range(k) for x in (call("read", f"read docs/notes_{i}.md"), res("read", prose(f"note {i}", 25)))]

transcripts = [
    T("cg-001", "en", [user("Fix the failing build. Never edit src/generated/ by hand."), call("bash", "$ make all"),
                       res("bash", build_log("src/net/socket.c", "E1042", "implicit declaration of function 'poll_wait'")),
                       *filler_calls(4), call("bash", "$ git status"), res("bash", "On branch main\nnothing to commit"),
                       asst("I will look at socket.c."), user("Go ahead."), call("read", "read src/net/socket.c"),
                       res("read", "int main(void) { return 0; }")],
      ["Never edit src/generated/ by hand", "src/net/socket.c", "E1042", "poll_wait", "exit code 2"]),
    T("cg-002", "tr", [user("Ödeme testini düzelt. tests/test_payments.py dışında hiçbir test dosyasını değiştirme."),
                       call("bash", "$ pytest -x tests/ --maxfail=1"),
                       res("bash", pytest_out("test_refund_rounding", "tests/test_payments.py::TestRefund")), *filler_calls(4),
                       asst("Yuvarlama hatasını inceliyorum."), user("Tamam."), call("read", "read app/money.py"), res("read", "def round_cents(x): ...")],
      ["tests/test_payments.py dışında hiçbir test dosyasını değiştirme", "test_refund_rounding", "AssertionError: expected 42 == 41",
       "--maxfail=1"]),
    T("cg-003", "en", [user("Summarise the rate-limit behaviour of the API and cite the source."), call("fetch", "fetch https://docs.example.com/api/limits"),
                       res("fetch", prose("limits", 40) + "\nSource: https://docs.example.com/api/limits#burst\nBurst limit: 120 requests per minute."),
                       *filler_calls(5), asst("Drafting the summary."), user("Keep it short."), call("read", "read README.md"), res("read", "# Example")],
      ["https://docs.example.com/api/limits#burst", "Burst limit: 120 requests per minute"]),
    T("cg-004", "en", [user("Update the deployment config; the replica count must stay at 3."), call("read", "read deploy/app.yaml"),
                       res("read", "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  replicas: 3\n  template:\n    spec:\n      containers:\n        - name: web\n          image: web:1.4.2"),
                       *filler_calls(5), asst("Changing the image tag."), user("ok"), call("bash", "$ kubectl diff -f deploy/app.yaml"), res("bash", "no changes")],
      ["the replica count must stay at 3", "replicas: 3", "image: web:1.4.2"]),
    T("cg-005", "tr", [user("Veritabanı geçişini çalıştırmadan önce onay al. Üretim ortamına asla doğrudan yazma."),
                       call("bash", "$ alembic upgrade head --sql"), res("bash", "\n".join(npm_noise(60)) + "\nALTER TABLE orders ADD COLUMN refunded_at TIMESTAMP;"),
                       *filler_calls(4), asst("SQL hazır."), user("Bekle."), call("read", "read migrations/env.py"), res("read", "config = context.config")],
      ["Veritabanı geçişini çalıştırmadan önce onay al", "Üretim ortamına asla doğrudan yazma", "ALTER TABLE orders ADD COLUMN refunded_at TIMESTAMP;", "--sql"]),
    T("cg-006", "en", [user("Find why login fails for SSO users."), call("bash", "$ grep -rn 'sso_callback' src/"),
                       res("bash", "src/auth/sso.py:41: def sso_callback(request):\nsrc/auth/sso.py:77:     raise PermissionError('E4031 token audience mismatch')"),
                       call("bash", "$ npm install"), res("bash", "\n".join(npm_noise(150) + progress(40))), *filler_calls(4),
                       asst("The audience check is the suspect."), user("Confirm with a test."), call("bash", "$ pytest tests/test_sso.py"), res("bash", "1 passed")],
      ["src/auth/sso.py:77", "E4031 token audience mismatch"]),
    T("cg-007", "en", [user("Investigate the crash in the image resizer."), call("bash", "$ python resize.py --input big.png"),
                       res("bash", 'Traceback (most recent call last):\n  File "/srv/app/resize.py", line 52, in <module>\n    main()\n  File "/srv/app/resize.py", line 31, in main\n    img = load(path)\nMemoryError: cannot allocate 4294967296 bytes'),
                       *filler_calls(6), asst("Large allocation."), user("Continue."), call("read", "read resize.py"), res("read", "def main(): ...")],
      ['File "/srv/app/resize.py", line 52', "MemoryError: cannot allocate 4294967296 bytes", "--input big.png"]),
    T("cg-008", "tr", [user("API yanıtındaki user_id alanını kontrol et ve kaynağı belirt."), call("fetch", "fetch https://api.example.com/v2/users/me"),
                       res("fetch", json.dumps({"user_id": "u_83921", "plan": "pro", "limits": {"daily": 5000}}, indent=2)),
                       *filler_calls(5), asst("Alan mevcut."), user("Devam et."), call("read", "read client.py"), res("read", "BASE='https://api.example.com/v2'")],
      ['"user_id": "u_83921"', "https://api.example.com/v2/users/me"]),
    T("cg-009", "en", [user("Review the diff for the cache layer."), call("bash", "$ git diff HEAD~1 -- cache/"),
                       res("bash", "diff --git a/cache/lru.py b/cache/lru.py\n--- a/cache/lru.py\n+++ b/cache/lru.py\n@@ -10,7 +10,7 @@\n-    if len(self.d) > self.cap:\n+    if len(self.d) >= self.cap:\n         self.evict()"),
                       *filler_calls(5), asst("Off-by-one change."), user("Is it correct?"), call("read", "read cache/lru.py"), res("read", "class LRU: ...")],
      ["+    if len(self.d) >= self.cap:", "diff --git a/cache/lru.py b/cache/lru.py"]),
    T("cg-010", "en", [user("Speed up the docker build; do not change the base image."), call("bash", "$ docker build -t app:dev ."),
                       res("bash", "\n".join(progress(80) + npm_noise(80)) + "\nStep 7/12 : RUN pip install -r requirements.txt\nWARNING: pip cache disabled; build took 412s"),
                       *filler_calls(4), asst("Caching the pip layer."), user("ok"), call("read", "read Dockerfile"), res("read", "FROM python:3.12-slim")],
      ["do not change the base image", "WARNING: pip cache disabled; build took 412s", "-t app:dev"]),
    T("cg-011", "tr", [user("Gece işinin neden zaman aşımına uğradığını bul."), call("bash", "$ journalctl -u nightly --since today"),
                       res("bash", "\n".join(f"nightly[{1000 + i}]: processed batch {i}" for i in range(140)) + "\nnightly[1140]: error: upstream timeout after 300s (E5040)\nnightly.service: Failed with result 'exit-code'."),
                       *filler_calls(4), asst("Zaman aşımı yukarı akışta."), user("Peki."), call("read", "read jobs/nightly.py"), res("read", "TIMEOUT = 300")],
      ["error: upstream timeout after 300s (E5040)", "Failed with result 'exit-code'", "--since today"]),
    T("cg-012", "en", [user("Plan the refactor of the billing module."), *filler_calls(8), asst("Here is the plan."),
                       user("Looks good, write it down."), call("write", "write docs/billing-plan.md"), res("write", "written")],
      ["Plan the refactor of the billing module", "Looks good, write it down"]),
]

# ------------------------------------------------------------ tool-pruner outputs
def P(id, lang, goal, output, essential):
    return {"id": id, "lang": lang, "goal": goal, "output": output, "essential": essential}


outputs = [
    P("tp-001", "en", "Fix the build error", build_log("src/core/parse.c", "E2201", "unknown type name 'size_tt'", 900),
      ["src/core/parse.c", "E2201", "unknown type name 'size_tt'", "make: *** [all] Error 2", "exit code 2"]),
    P("tp-002", "en", "Find the failing test", pytest_out("test_tz_offset", "tests/test_time.py::TestTZ", 700),
      ["tests/test_time.py::TestTZ::test_tz_offset FAILED", "AssertionError: expected 42 == 41", "1 failed, 699 passed"]),
    P("tp-003", "en", "Install dependencies and report problems", "\n".join(npm_noise(700) + ["npm WARN deprecated request@2.88.2: request has been deprecated",
                                                                                              "npm ERR! code ERESOLVE", "npm ERR! peer react@\"^17\" from legacy-widget@1.2.0"]),
      ["npm WARN deprecated request@2.88.2", "npm ERR! code ERESOLVE", "legacy-widget@1.2.0"]),
    P("tp-004", "en", "Pull the image", "\n".join(progress(600) + ["Status: Downloaded newer image for registry.local/app:2.3.1", "Digest: sha256:4f9c0e"]),
      ["Downloaded newer image for registry.local/app:2.3.1", "Digest: sha256:4f9c0e"]),
    P("tp-005", "tr", "Gece işinin hatasını bul", "\n".join([f"nightly[{1000 + i}]: processed batch {i}" for i in range(800)]
                                                          + ["nightly[1800]: error: disk quota exceeded on /var/data (E5007)", "nightly.service: Failed with result 'exit-code'."]),
      ["error: disk quota exceeded on /var/data (E5007)", "Failed with result 'exit-code'"]),
    P("tp-006", "en", "Check the API response", json.dumps({"items": [{"id": i, "name": f"item-{i}", "price": i * 3} for i in range(400)], "next": "cursor_abc"}),
      ['"next": "cursor_abc"', '"id": 399']),
    P("tp-007", "en", "Review the diff", "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n" + "\n".join(f"+line {i}" for i in range(900)),
      ["+line 0", "+line 899"]),
    P("tp-008", "en", "Find where the config is loaded", "\n".join([f"src/mod_{i}/util.py:{i}: import os" for i in range(500)]
                                                              + ["src/settings/loader.py:12: def load_config(path):"]),
      ["src/settings/loader.py:12: def load_config(path):"]),
    P("tp-009", "tr", "Testlerin sonucunu raporla", pytest_out("test_kdv_hesabi", "tests/test_vergi.py::TestKDV", 650),
      ["tests/test_vergi.py::TestKDV::test_kdv_hesabi FAILED", "1 failed, 649 passed"]),
    P("tp-010", "en", "Short command", "ok\nall good", ["all good"]),
    P("tp-011", "en", "Run the linter", "\n".join([f"checking file {i} of 900" for i in range(900)] + ["src/api/routes.py:203:5: W0612 unused variable 'resp'",
                                                                                                   "Your code has been rated at 9.87/10"]),
      ["src/api/routes.py:203:5: W0612 unused variable 'resp'", "rated at 9.87/10"]),
    P("tp-012", "en", "Download the dataset", "\n".join(progress(500) + ["Saved to /data/raw/corpus-2026.tar.gz (3.1 GB)", "Checksum OK"]),
      ["Saved to /data/raw/corpus-2026.tar.gz", "Checksum OK"]),
]

if __name__ == "__main__":
    here = Path(__file__).parent
    meta = {"authored": "2026-10-14", "provenance": "R3.2G session, before any ContextGate/pruner run; synthetic; no human review",
            "metric": "a missing `essential` string in the derived view is a false drop"}
    for t in transcripts:
        for i, it in enumerate(t["items"]):
            it["id"] = f"{t['id']}-{i:02d}"
    (here / "contextgate-suite-v1.yaml").write_text(yaml.safe_dump({"version": 1, "suite": "contextgate-suite-v1", **meta,
                                                                    "transcripts": transcripts}, sort_keys=False, allow_unicode=True, width=200))
    (here / "toolpruner-suite-v1.yaml").write_text(yaml.safe_dump({"version": 1, "suite": "toolpruner-suite-v1", **meta,
                                                                   "outputs": outputs}, sort_keys=False, allow_unicode=True, width=200))
    print(len(transcripts), len(outputs))
