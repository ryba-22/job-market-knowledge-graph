from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from ingestion.classification02 import POLICY_VERSION, assess_row
from ingestion.clean_aplikuj_cache import compressed_rows, read_gz
from ingestion.run_classification02 import run, verify_output


def source_row(sid, title, industry, description):
    return {
        "source":"aplikuj", "source_posting_id":sid, "title":title,
        "url":f"https://www.aplikuj.pl/oferta/{sid}/test",
        "revision_id":f"rev-{sid}", "raw_payload_sha256":f"source-{sid}",
        "source_projection":{"industry":industry},
        "normalized_projection":{"semantic_content":{"jobposting_json_ld":{"description":description}}},
    }


@pytest.mark.parametrize("title,industry,description,expected",[
    ("Frontend Developer","Informatyk","Doświadczenie z React i TypeScript, tworzenie aplikacji webowych.","IT_CONFIRMED"),
    ("Senior Data Engineer","Informatyk","Designing data pipelines and SQL databases in AWS.","IT_CONFIRMED"),
    ("Administrator sieci","Informatyk","Administrowanie serwerami oraz zarządzanie systemami IT.","IT_CONFIRMED"),
    ("Nauczyciel informatyki","Nauczyciel","Praca w szkole, prowadzenie lekcji informatyki.","NON_IT_CONFIRMED"),
    ("Programista/Informatyk- praca w tygodniu","Nauczyciel","Technikum zatrudni nauczycieli programowania.","NON_IT_CONFIRMED"),
    ("Kierowca międzynarodowy PL IT DE","Kierowca","Prowadzenie pojazdu i przewóz towarów.","NON_IT_CONFIRMED"),
    ("Programista Robotów Spawalniczych","Programista","Programowanie robotów spawalniczych Panasonic i spawanie.","NON_IT_CONFIRMED"),
    ("Operator CNC","Programista","Obsługa obrabiarek i programowanie frezarek CNC.","NON_IT_CONFIRMED"),
    ("Przedstawiciel handlowy branża IT","Handlowiec","Pozyskiwanie klientów, przygotowywanie ofert sprzedażowych.","NON_IT_CONFIRMED"),
    ("Doradca Klienta","Handlowiec","Obsługa klientów lombardu.","NON_IT_CONFIRMED"),
    ("Specjalista ds. ITAR / Export Compliance","Inny","Compliance i przepisy eksportowe ITAR.","REVIEW_REQUIRED"),
    ("Programista k/m","Programista","Znajomość plików DXF i STEP.","REVIEW_REQUIRED"),
    ("Obsługa sklepu internetowego / Junior Front-end Developer","Informatyk","Tworzenie aplikacji React i praca przy sklepie.","REVIEW_REQUIRED"),
    ("Presales Engineer","Informatyk","Znajomość SQL i API, sprzedaż rozwiązań IT.","REVIEW_REQUIRED"),
    ("Specjalista","Informatyk","Pracuj w świetnej firmie, benefity i szkolenia.","REVIEW_REQUIRED"),
])
def test_adversarial_roles(title,industry,description,expected):
    row = source_row("test", title, industry, description)
    original = deepcopy(row)
    result=assess_row(row)
    assert result["status"] == expected
    assert result["policy_version"] == POLICY_VERSION
    assert row == original
    from ingestion.aplikuj_it_scope import normalized
    d=normalized(description)
    for ev in result["evidence"]:
        assert ev["span"]
        if ev["field"] == "description":
            assert ev["span"] in d


def test_offline_run_preserves_archive_and_reconciles_all_ids(tmp_path,monkeypatch):
    from ingestion import run_classification02 as module
    src=tmp_path / "archive"
    dir=src / "aplikuj" / "0"
    dir.mkdir(parents=True)
    rows=[
        source_row("1","Frontend Developer","Informatyk","React, tworzenie aplikacji webowych."),
        source_row("2","Nauczyciel informatyki","Nauczyciel","Praca w szkole, prowadzenie lekcji."),
        source_row("3","Programista k/m","Inny","Znajomość DXF i STEP."),
    ]
    baseline=[
        {"source_posting_id":r["source_posting_id"],"raw_payload_sha256":r["raw_payload_sha256"],
         "assessment":{"status":"REVIEW_REQUIRED"}} for r in rows
    ]
    cb,cm=compressed_rows(rows)
    ab,am=compressed_rows(baseline)
    corpus=dir/"corpus.jsonl.gz"
    past=dir/"assessments.jsonl.gz"
    corpus.write_bytes(cb)
    past.write_bytes(ab)
    manifest={"scope":"it-category-v2","corpus":cm,"raw_archive":{"compressed_sha256":"sha-raw"},
              "assessment_archive":am}
    (dir/"manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(module, "verify_source", lambda _: {"status":"PASS","errors":[],"postings":3,"v2_chunks":1})
    original_corpus=corpus.read_bytes()
    original_prior=past.read_bytes()
    target=tmp_path/"classification"
    result=run(src,target)
    assert result["source_postings"]==3
    assert result["status_counts"]=={"IT_CONFIRMED":1,"NON_IT_CONFIRMED":1,"REVIEW_REQUIRED":1}
    assert result["assessment_verification"]=="PASS"
    assert corpus.read_bytes()==original_corpus
    assert past.read_bytes()==original_prior
    assert len(read_gz(target/"assessments.jsonl.gz"))==3
    assert [r["source_posting_id"] for r in read_gz(target/"review-queue.jsonl.gz")]==["3"]
    assert verify_output(src,target)["status"]=="PASS"
    # Reassessment over the same source is deterministic.
    first=(target/"assessments.jsonl.gz").read_bytes()
    run(src,target)
    assert first==(target/"assessments.jsonl.gz").read_bytes()
    (target/"assessments.jsonl.gz").write_bytes(b"corrupted")
    assert verify_output(src,target)["status"]=="FAIL"


def test_missing_source_archive_is_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="source archival verification failed"):
        run(tmp_path/"missing",tmp_path/"result")
    assert not (tmp_path/"result").exists()
