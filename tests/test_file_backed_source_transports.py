import json

import ingestion.acquire_file_backed as a
from ingestion.model import ParsedPosting


class FakeResponse:
    text = "<html>ok</html>"
    url = "https://example.test/final"
    status_code = 200
    headers = {"content-type": "text/html"}

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        return FakeResponse()


class FakeJjitAdapter:
    def parse_detail(self, payload, url):
        assert payload == "<html>ok</html>"
        assert url == "https://example.test/final"
        return ParsedPosting(
            source="justjoinit",
            source_posting_id="jj-1",
            url=url,
            title="Role",
            company_mention="Company",
            body_text="Body",
        )


def _write_plan(path, source, row):
    path.write_text(json.dumps({
        "chunks": [{
            "source": source,
            "chunk_index": 0,
            "count": 1,
            "rows": [row],
        }]
    }))


def test_file_backed_justjoinit_uses_direct_adapter_transport(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    _write_plan(plan, "justjoinit", {
        "source": "justjoinit",
        "source_posting_id": "jj-1",
        "url": "https://example.test/job/jj-1",
        "known": False,
    })
    monkeypatch.setitem(a.ADAPTERS, "justjoinit", FakeJjitAdapter())
    monkeypatch.setattr(a.httpx, "Client", FakeClient)

    manifest = a.acquire(
        str(plan),
        "justjoinit",
        0,
        str(tmp_path / "out"),
        str(tmp_path / "raw"),
        0,
        1,
    )

    assert manifest["postings"] == 1
    assert manifest["errors"] == []


def test_file_backed_theprotocol_uses_official_mcp_details(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    search = {
        "offerId": "tp-1",
        "groupId": "group-1",
        "title": "Role",
        "url": "https://theprotocol.it/example",
    }
    _write_plan(plan, "theprotocol", {
        "source": "theprotocol",
        "source_posting_id": "tp-1",
        "url": search["url"],
        "known": False,
        "group_id": "group-1",
        "mcp_search_row": search,
    })
    monkeypatch.setattr(a.httpx, "Client", FakeClient)
    monkeypatch.setattr(a, "fetch_groups_sync", lambda ids: [{"title": "Role", "offerUrl": search["url"]}])

    def parse(search_row, details):
        assert search_row == search
        assert details["title"] == "Role"
        return ParsedPosting(
            source="theprotocol",
            source_posting_id="tp-1",
            url=search["url"],
            title="Role",
            company_mention="Company",
            body_text=json.dumps(details),
        )

    monkeypatch.setattr(a, "parse_theprotocol", parse)

    manifest = a.acquire(
        str(plan),
        "theprotocol",
        0,
        str(tmp_path / "out"),
        str(tmp_path / "raw"),
        0,
        1,
    )

    assert manifest["postings"] == 1
    assert manifest["errors"] == []
