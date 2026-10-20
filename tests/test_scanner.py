import json
from datetime import date

import yaml

from scanner.checks import number_in, quote_in, unsupported_numbers
from scanner.config import DATA, ROOT, load
from scanner.months import previous, window
from scanner.sources import record_hash
from scanner.triage import Judgement, apply
from scanner.validate import check_development, validate_all

ROUTE_IDS = {r["id"] for r in load("routes")}


def test_month_windows():
    assert window("2026-09") == (date(2026, 9, 1), date(2026, 9, 30))
    assert window("2028-02")[1] == date(2028, 2, 29)
    assert previous(date(2026, 10, 3)) == "2026-09"
    assert previous(date(2027, 1, 3)) == "2026-12"


def test_numbers_must_be_whole_numbers():
    assert not number_in("12", "results from 2012")
    assert not number_in("12", "a 12.5 % gain")
    assert number_in("12", "a 12 % gain")
    assert number_in("3.4", "modulus (63 MPa and 3.4 GPa)")
    assert unsupported_numbers("Capacity of 12 kt", "planned in 2012") == ["12"]


def test_quote_normalisation():
    assert quote_in("PLA   blend", "A new PLA blend for films")
    assert quote_in("“stiff” – tough", '"stiff" - tough')
    assert not quote_in("", "anything")


def rec(**kw):
    return {"id": "doi:x", "title": "Stereocomplex PLA foams", "abstract": "We report stereocomplex PLA foams with a melting point of 220 °C.",
            "published_date": "2026-09-10", **kw}


def J(**kw):
    base = dict(id="doi:x", route="pla", novelty_type="new-formulation-or-application", relevance=0.9, summary="Stereocomplex PLA foams are reported.",
                quote="We report stereocomplex PLA foams", quote_location="abstract")
    return Judgement(**{**base, **kw})


def test_quote_must_be_verbatim():
    good = apply(rec(), J(), ROUTE_IDS, "2026-09-30")
    assert not good["hidden"] and good["quote"]
    bad = apply(rec(), J(quote="record-breaking heat resistance"), ROUTE_IDS, "2026-09-30")
    assert bad["hidden"] and not bad["summary"] and "quote-not-in-source" in bad["flags"]


def test_summary_numbers_must_be_in_quote():
    bad = apply(rec(), J(summary="Foams melt at 220 °C."), ROUTE_IDS, "2026-09-30")
    assert bad["hidden"] and "number-not-in-quote" in bad["flags"]
    ok = apply(rec(), J(summary="Foams melt at 220 °C.", quote="a melting point of 220 °C"), ROUTE_IDS, "2026-09-30")
    assert not ok["hidden"]


def test_unknown_ids_low_relevance_and_cutoff_hidden():
    assert apply(rec(), J(route="magic"), ROUTE_IDS, "2026-09-30")["hidden"]
    assert apply(rec(), J(novelty_type="brand-new"), ROUTE_IDS, "2026-09-30")["hidden"]
    assert apply(rec(), J(relevance=0.59), ROUTE_IDS, "2026-09-30")["hidden"]
    late = apply(rec(published_date="2026-10-02"), J(), ROUTE_IDS, "2026-09-30")
    assert late["hidden"] and "after-cutoff" in late["flags"]


def test_record_hash_is_stable():
    a = {"doi": "10.1/ABC", "url": "", "title": "PLA: a review"}
    assert record_hash(a) == record_hash({**a, "doi": "10.1/abc", "title": "PLA - A Review"})


def dev(**kw):
    d = {"id": "t", "review": {"status": "draft"}, "sources": [{"url": "https://x", "published": "2026-09-05"}],
         "capacity": {"value": "Not disclosed"}, "climate": {"value": "Not disclosed"}}
    d.update(kw)
    return d


def test_development_rules():
    assert check_development(dev(), "2026-09-30") == []
    assert any("no quote" in e for e in check_development(dev(trl={"value": "6"}), "2026-09-30"))
    assert any("number 30" in e for e in check_development(dev(capacity={"value": "30 kt", "status": "announced", "quote": "3 kt line", "source": "s"}), "2026-09-30"))
    assert any("without status" in e for e in check_development(dev(capacity={"value": "30 kt", "quote": "a 30 kt plant", "source": "s"}), "2026-09-30"))
    assert any("boundaries" in e for e in check_development(dev(climate={"value": "1.2", "quote": "1.2 kg", "source": "s", "boundary": "cradle-to-gate", "comparator_boundary": "cradle-to-grave", "reduction": "40%"}), "2026-09-30"))
    assert any("after cutoff" in e for e in check_development(dev(sources=[{"url": "https://x", "published": "2026-10-05"}]), "2026-09-30"))
    assert any("signed without" in e for e in check_development(dev(review={"status": "signed"}), "2026-09-30"))


def test_structure_hydrolysis_catches_wrong_stereo():
    from rdkit import Chem

    from scanner.structures import cap_and_hydrolyse

    l_lactic = Chem.MolToInchiKey(Chem.MolFromSmiles("C[C@H](O)C(=O)O"))
    assert cap_and_hydrolyse("*O[C@@H](C)C(*)=O") == {l_lactic}
    assert cap_and_hydrolyse("*O[C@H](C)C(*)=O") != {l_lactic}


def test_repository_data_is_valid():
    assert validate_all() == []


def test_published_leads_have_no_abstracts():
    for path in (DATA / "leads").glob("*.json"):
        for c in json.loads(path.read_text())["leads"]:
            assert c.get("route") == "untriaged" or "abstract" not in c
            if not c.get("hidden"):
                assert c["route"] in ROUTE_IDS and c["quote"] and c["relevance"] >= 0.6


def test_flash_is_default_and_drafting_unset():
    cfg = yaml.safe_load((ROOT / "config" / "llm.yaml").read_text())
    assert cfg["triage_model"] == "deepseek-flash"
    assert cfg["draft_model"] is None and cfg["max_draft_calls"] <= 3
    assert cfg["max_calls_per_run"] == 60
