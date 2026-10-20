"""Authors evals/data/modules/wakegate-suite-v1.yaml (R3.2G). Labels are fixed from explicit rules BEFORE any run.

must_wake    missing it is a FALSE NEGATIVE (the safety metric)
should_defer waking is an unnecessary wake (the cost metric)
wake_ok      waking is expected by rule; deferring would also be harmless
Run: uv run python evals/data/modules/author_wakegate_suite.py
"""
from pathlib import Path

import yaml

W_HR, W_HR_TR = ("A reply from Dana (HR) about scheduling my second-round interview",
                 "İK'dan Dana'nın ikinci tur mülakat planlamasıyla ilgili yanıtı")
W_PRICE, W_PRICE_TR = "The laptop price to drop below 1000 USD", "Dizüstü bilgisayar fiyatının 1000 USD'nin altına düşmesi"
W_CI, W_CI_TR = "The nightly integration test run to finish", "Gece entegrasyon test çalışmasının bitmesi"
W_PR, W_PR_TR = "Code review comments on pull request 482", "482 numaralı çekme isteğine kod inceleme yorumları"
OLD_PRICE = {"price_usd": 1249}

cases = []


def c(id, lang, waiting, ev, gold, family, prev_obs=None, skipped=0):
    cases.append({"id": id, "lang": lang, "family": family, "waiting_for": waiting, "event": ev,
                  "previous_observation": prev_obs, "skipped": skipped, "gold": gold})


# 1. must wake by a deterministic rule (the model must never be consulted)
c("wg-rule-001", "en", W_PR, {"kind": "message", "summary": "Please stop the deploy, I changed my mind", "from_user": True}, "must_wake", "rule_user")
c("wg-rule-002", "tr", W_PR_TR, {"kind": "message", "summary": "Lütfen dağıtımı durdur, fikrimi değiştirdim", "from_user": True}, "must_wake", "rule_user")
c("wg-rule-003", "en", W_CI, {"kind": "ci", "summary": "Nightly integration run FAILED: 3 tests failed in payments", "source": "ci"}, "must_wake", "rule_failure")
c("wg-rule-004", "tr", W_CI_TR, {"kind": "ci", "summary": "Gece entegrasyon çalışması başarısız: ödemelerde 3 test hata verdi", "source": "ci"}, "must_wake", "rule_failure")
c("wg-rule-005", "en", W_PR, {"kind": "alert", "summary": "Leaked API key detected in commit a1b2c3", "source": "secret-scanner"}, "must_wake", "rule_security")
c("wg-rule-006", "tr", W_PR_TR, {"kind": "alert", "summary": "a1b2c3 commitinde sızdırılmış parola tespit edildi", "source": "tarayıcı"}, "must_wake", "rule_security")
c("wg-rule-007", "en", W_PR, {"kind": "webhook", "summary": "Production database migration awaiting sign-off", "markers": ["approval"], "requires_approval": True}, "must_wake", "rule_approval")
c("wg-rule-008", "tr", W_PR_TR, {"kind": "webhook", "summary": "Üretim veritabanı geçişi onay bekliyor", "markers": ["onay"], "requires_approval": True}, "must_wake", "rule_approval")
c("wg-rule-009", "en", W_PRICE, {"kind": "webhook", "summary": "Payment method change requested for the shared account", "risk": "high"}, "must_wake", "rule_risk")
c("wg-rule-010", "tr", W_PRICE_TR, {"kind": "webhook", "summary": "Ortak hesap için ödeme yöntemi değişikliği istendi", "risk": "high"}, "must_wake", "rule_risk")
c("wg-rule-011", "en", W_HR, {"kind": "calendar", "summary": "Interview prep reminder", "deadline_minutes": 30}, "must_wake", "rule_deadline")
c("wg-rule-012", "tr", W_HR_TR, {"kind": "calendar", "summary": "Mülakat hazırlık hatırlatması", "deadline_minutes": 20}, "must_wake", "rule_deadline")
c("wg-rule-013", "en", W_CI, {"kind": "alert", "summary": "Build agent disk full, job crashed", "source": "monitor"}, "must_wake", "rule_failure")
c("wg-rule-014", "tr", W_CI_TR, {"kind": "alert", "summary": "Derleme ajanının diski doldu, iş çöktü", "source": "izleme"}, "must_wake", "rule_failure")
# 2. unchanged timer observation -> defer by rule
for i, (lang, w, obs) in enumerate([("en", W_PRICE, OLD_PRICE), ("tr", W_PRICE_TR, OLD_PRICE),
                                    ("en", W_CI, {"status": "running", "done": 41}), ("tr", W_CI_TR, {"status": "running", "done": 41})]):
    c(f"wg-nochange-{i + 1:03d}", lang, w, {"kind": "timer", "observation": obs}, "should_defer", "rule_no_change", prev_obs=obs)
# 3. skip limit reached -> wake by rule
c("wg-skip-001", "en", W_HR, {"kind": "email", "summary": "Weekly newsletter: 7 stories about AI", "source": "news@medium.com"}, "wake_ok", "skip_limit", skipped=10)
c("wg-skip-002", "tr", W_HR_TR, {"kind": "email", "summary": "Haftalık bülten: yapay zekâ hakkında 7 yazı", "source": "bulten@ornek.com"}, "wake_ok", "skip_limit", skipped=10)
# 4. model-judged, RELEVANT to what the agent waits for -> must wake
REL = [("en", W_HR, {"kind": "email", "summary": "Re: second-round interview, are you free Thursday at 14:00?", "source": "dana@acme.com"}),
       ("tr", W_HR_TR, {"kind": "email", "summary": "Ynt: ikinci tur mülakat, perşembe 14:00 uygun musunuz?", "source": "dana@acme.com"}),
       ("en", W_PRICE, {"kind": "timer", "observation": {"price_usd": 949}}),
       ("tr", W_PRICE_TR, {"kind": "timer", "observation": {"price_usd": 949}}),
       ("en", W_CI, {"kind": "webhook", "summary": "Nightly integration run finished: all 812 tests passed", "source": "ci"}),
       ("tr", W_CI_TR, {"kind": "webhook", "summary": "Gece entegrasyon çalışması bitti: 812 testin tamamı geçti", "source": "ci"}),
       ("en", W_PR, {"kind": "email", "summary": "New review comments on PR 482: please rename the parser module", "source": "github"}),
       ("tr", W_PR_TR, {"kind": "email", "summary": "482 numaralı PR'a yeni inceleme yorumları: ayrıştırıcı modülünü yeniden adlandırın", "source": "github"}),
       ("en", W_HR, {"kind": "message", "summary": "Dana from HR left you a voicemail about the interview slot", "source": "phone"}),
       ("tr", W_HR_TR, {"kind": "message", "summary": "İK'dan Dana mülakat saati hakkında sesli mesaj bıraktı", "source": "telefon"}),
       ("en", W_PRICE, {"kind": "email", "summary": "Price alert: the laptop on your list is now 899 USD", "source": "shop"}),
       ("tr", W_PRICE_TR, {"kind": "email", "summary": "Fiyat uyarısı: listendeki dizüstü bilgisayar artık 899 USD", "source": "magaza"})]
for i, (lang, w, ev) in enumerate(REL):
    c(f"wg-rel-{i + 1:03d}", lang, w, ev, "must_wake", "model_relevant", prev_obs=OLD_PRICE if ev["kind"] == "timer" else None)
# 5. model-judged, IRRELEVANT -> should defer
IRR = [("en", W_HR, {"kind": "email", "summary": "Your daily digest: 7 stories about productivity", "source": "noreply@medium.com"}),
       ("tr", W_HR_TR, {"kind": "email", "summary": "Günlük özetiniz: verimlilik hakkında 7 hikâye", "source": "noreply@medium.com"}),
       ("en", W_PRICE, {"kind": "timer", "observation": {"price_usd": 1239}}),
       ("tr", W_PRICE_TR, {"kind": "timer", "observation": {"price_usd": 1239}}),
       ("en", W_CI, {"kind": "webhook", "summary": "Nightly run progress: 420 of 812 tests done", "source": "ci"}),
       ("tr", W_CI_TR, {"kind": "webhook", "summary": "Gece çalışması ilerleme: 812 testin 420'si tamamlandı", "source": "ci"}),
       ("en", W_PR, {"kind": "email", "summary": "GitHub: someone starred your repository", "source": "github"}),
       ("tr", W_PR_TR, {"kind": "email", "summary": "GitHub: biri deponuza yıldız verdi", "source": "github"}),
       ("en", W_HR, {"kind": "email", "summary": "Promotion: 20% off conference tickets this week", "source": "events@ticketing.com"}),
       ("tr", W_HR_TR, {"kind": "email", "summary": "Kampanya: bu hafta konferans biletlerinde %20 indirim", "source": "etkinlik@bilet.com"}),
       ("en", W_PRICE, {"kind": "email", "summary": "Shop newsletter: new phone cases in stock", "source": "shop"}),
       ("tr", W_PRICE_TR, {"kind": "email", "summary": "Mağaza bülteni: yeni telefon kılıfları stokta", "source": "magaza"}),
       ("en", W_CI, {"kind": "webhook", "summary": "Dependency bot opened a PR to bump a dev dependency", "source": "bot"}),
       ("tr", W_CI_TR, {"kind": "webhook", "summary": "Bağımlılık botu bir geliştirme bağımlılığını güncellemek için PR açtı", "source": "bot"})]
for i, (lang, w, ev) in enumerate(IRR):
    c(f"wg-irr-{i + 1:03d}", lang, w, ev, "should_defer", "model_irrelevant", prev_obs=OLD_PRICE if ev["kind"] == "timer" else None)

if __name__ == "__main__":
    doc = {"version": 1, "suite": "wakegate-suite-v1", "authored": "2026-10-14",
           "provenance": "Authored by the R3.2G session before any WakeGate run (this script). Labels follow explicit rules and "
                         "the relevance of the event to waiting_for. No human review.",
           "cases": cases}
    out = Path(__file__).with_name("wakegate-suite-v1.yaml")
    out.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200))
    print(out, len(cases))
