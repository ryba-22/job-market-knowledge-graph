import asyncio

import ingestion.theprotocol_mcp as tp


class FakeResult:
    def __init__(self,payload):
        self.structuredContent=payload
        self.content=[]


class FakeSession:
    def __init__(self):
        self.search_pages=[]
        self.details=[]

    async def initialize(self):
        return None

    async def call_tool(self,name,arguments):
        if name=="search_job_offers":
            page=arguments["pageNumber"]
            self.search_pages.append(page)
            start=(page-1)*50
            offers=[
                {"offerId":f"id-{i}","groupId":f"g-{i}","title":f"Role {i}"}
                for i in range(start,start+50)
            ]
            return FakeResult({"offers":offers})
        if name=="get_job_offer_details":
            gid=arguments["groupId"]
            self.details.append(gid)
            return FakeResult({"title":f"Role {gid.split('-')[1]}","offerUrl":f"https://example.test/{gid}"})
        raise AssertionError(name)


class FakeStreams:
    async def __aenter__(self):
        return (object(),object(),None)

    async def __aexit__(self,*args):
        return False


def test_fetch_batch_paginates_beyond_50(monkeypatch):
    session=FakeSession()
    monkeypatch.setattr(tp,"streamablehttp_client",lambda _:FakeStreams())
    monkeypatch.setattr(tp,"ClientSession",lambda *args: _SessionContext(session))
    rows=asyncio.run(tp.fetch_batch(100))
    assert len(rows)==100
    assert session.search_pages==[1,2]
    assert len(session.details)==100


class _SessionContext:
    def __init__(self,session):
        self.session=session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self,*args):
        return False
