"""Authors evals/data/retrieval-suite-v1.yaml (R3.5). Synthetic SecondBrain-style notes; model-assisted, NOT human reviewed.
12 topics x 3 notes (answer / lexical decoy / other), 12 EN+TR queries (4 deliberately use words the answer note does not),
plus 10 citation cases (supported, fabricated source, wrong quote, paraphrase, source outside the selected pack). Refuses to overwrite."""
from pathlib import Path

import yaml

N = []   # (id, text)
def note(i, text): N.append({"source_id": i, "path": f"notes/{i}.md", "text": text})

note("backup-a", "Database backups run nightly at 02:00 and are kept for 35 days before deletion.")
note("backup-b", "The backup of the laptop photos is manual; nobody checks it on a schedule.")
note("backup-c", "Quarterly planning happens in the first week of each quarter.")
note("rate-a", "The public API allows 600 requests per minute per key; bursts above that receive HTTP 429.")
note("rate-b", "Our request for a higher limit was discussed in the vendor call but never filed.")
note("rate-c", "Office plants are watered on Mondays.")
note("deploy-a", "Production deploys require a named human approver; the approver must not be the author of the change.")
note("deploy-b", "The deploy script prints the author name and the approver field for staging runs.")
note("deploy-c", "The cafeteria menu rotates every two weeks.")
note("tls-a", "TLS certificates are renewed 21 days before expiry by the platform team using the shared renewal job.")
note("tls-b", "A certificate-themed team lunch happened last month.")
note("tls-c", "Parking permits are issued by facilities.")
note("onboard-a", "New engineers get repository access on day one and production access only after the security module is completed.")
note("onboard-b", "The onboarding buddy shares the access request form for the meeting rooms.")
note("onboard-c", "The VPN client is installed from the self-service portal.")
note("interview-a", "Interview feedback must be submitted within 24 hours using the structured scorecard.")
note("interview-b", "The interview room on floor 3 has a broken projector.")
note("interview-c", "Salary bands are reviewed annually in March.")
note("expense-a", "Expenses above 250 EUR need a manager's written approval before purchase.")
note("expense-b", "The expense report template has a column for the cost center and a column for the approval date.")
note("expense-c", "Team offsite dates are fixed for the second week of June.")
note("postmortem-a", "Every sev-1 incident gets a blameless postmortem published within five working days.")
note("postmortem-b", "The postmortem template folder was moved to the shared drive.")
note("postmortem-c", "The on-call phone is charged at the front desk.")
note("migrate-a", "Schema migrations may only run in the Tuesday and Thursday 22:00-23:00 maintenance window.")
note("migrate-b", "The migration guide for the old CRM is archived and no longer maintained.")
note("migrate-c", "Stand-up is at 09:30 and takes fifteen minutes.")
note("naming-a", "Services are named kebab-case with the team prefix, for example pay-ledger-api.")
note("naming-b", "The team prefix list was copied from an older wiki page.")
note("naming-c", "Fridge cleaning happens on Fridays.")
note("oncall-a", "The on-call rotation changes every Monday at 10:00 and the handover note goes into the ops channel.")
note("oncall-b", "On-call compensation is described in the HR handbook.")
note("oncall-c", "Printer supplies are ordered by facilities.")
note("retain-a", "Customer chat logs are deleted after 90 days unless a legal hold applies.")
note("retain-b", "The legal hold template lives with the compliance team.")
note("retain-c", "Bicycle storage is in the basement.")
note("yedek-a", "Veritabanı yedekleri her gece 02:00'de alınır ve 35 gün saklanır.")
note("yedek-b", "Fotoğrafların yedeği elle alınır ve kimse düzenli kontrol etmez.")
note("onay-a", "Üretim dağıtımları için adı belli bir insan onaylayıcı gerekir; onaylayıcı değişikliği yazan kişi olamaz.")
note("onay-b", "Dağıtım betiği hazırlık ortamında yazar adını ve onaylayıcı alanını yazdırır.")
note("sertifika-a", "TLS sertifikaları süresi dolmadan 21 gün önce platform ekibi tarafından yenilenir.")
note("sertifika-b", "Geçen ay sertifika temalı bir takım yemeği yapıldı.")
Q = [
 ("q01", "en", "How long are database backups kept?", ["backup-a"], "lexical"),
 ("q02", "en", "What happens when I exceed the API request limit?", ["rate-a"], "lexical"),
 ("q03", "en", "Who can approve a production deploy?", ["deploy-a"], "lexical"),
 ("q04", "en", "When are certificates renewed before they expire?", ["tls-a"], "lexical"),
 ("q05", "en", "When do new hires get production access?", ["onboard-a"], "lexical"),
 ("q06", "en", "How quickly must interviewers submit feedback?", ["interview-a"], "lexical"),
 ("q07", "en", "Do I need sign-off to buy something costing 300 EUR?", ["expense-a"], "vocab_mismatch"),
 ("q08", "en", "What is required after a severity one outage?", ["postmortem-a"], "vocab_mismatch"),
 ("q09", "en", "When may we change the database structure in production?", ["migrate-a"], "vocab_mismatch"),
 ("q10", "en", "How do we name a new service?", ["naming-a"], "lexical"),
 ("q11", "en", "How long do we keep customer chat records?", ["retain-a"], "vocab_mismatch"),
 ("q12", "tr", "Veritabanı yedekleri ne kadar süre saklanır?", ["yedek-a"], "lexical"),
 ("q13", "tr", "Üretim dağıtımını kim onaylayabilir?", ["onay-a"], "lexical"),
 ("q14", "tr", "Sertifikalar ne zaman yenilenir?", ["sertifika-a"], "lexical"),
 ("q15", "en", "Who is on call this week and when does it rotate?", ["oncall-a"], "lexical"),
]
C = [
 ("c01", [{"source_id": "backup-a", "quote": "kept for 35 days"}], ["supported"]),
 ("c02", [{"source_id": "backup-a", "quote": "kept for 90 days"}], ["quote_not_in_source"]),
 ("c03", [{"source_id": "backup-z", "quote": "kept for 35 days"}], ["unknown_source"]),
 ("c04", [{"source_id": "rate-a", "quote": "600 requests per minute"}, {"source_id": "rate-a", "quote": "the API is limited to 600 req/min"}], ["supported", "quote_not_in_source"]),
 ("c05", [{"source_id": "deploy-a", "quote": "Production deploys require a NAMED human   approver"}], ["supported"]),
 ("c06", [{"source_id": "tls-c", "quote": "Parking permits are issued by facilities."}], ["source_not_selected"]),
 ("c07", [{"source_id": "tls-a", "quote": ""}], ["empty_quote"]),
 ("c08", [{"source_id": None, "quote": "x"}, "not a dict"], ["unknown_source", "unknown_source"]),
 ("c09", [{"source_id": "yedek-a", "quote": "35 gün saklanır"}], ["supported"]),
 ("c10", [{"source_id": "expense-a", "quote": "need a manager's written approval"}, {"source_id": "expense-b", "quote": "approval is always automatic"}], ["supported", "source_not_selected"])   # expense-b is not in the selected pack: pack membership is checked before the quote (documented precedence),
]
data = {"version": 1, "suite": "retrieval-suite-v1", "authored": "2026-10-16",
        "limitations": "Synthetic, tiny, model-assisted labels (no human review). Vocabulary-mismatch queries are included on purpose: lexical selection is expected to struggle there and embeddings are not available to compare.",
        "pool": N, "queries": [{"id": a, "lang": b, "query": c, "relevant": d, "kind": e} for a, b, c, d, e in Q],
        "citation_cases": [{"id": a, "citations": b, "expect": c, "selected_only": ["backup-a", "rate-a", "deploy-a", "tls-a", "yedek-a", "expense-a"]} for a, b, c in C]}
p = Path(__file__).parent / "retrieval-suite-v1.yaml"
if p.exists():
    raise RuntimeError("refusing to overwrite")
p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
print("wrote", p.name, len(N), "notes")
