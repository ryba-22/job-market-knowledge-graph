from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .model import ParsedPosting, norm_text


MCP_URL = "https://grus-api.theprotocol.it/mcp"


def _payload(result) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            try:
                value = json.loads(text)
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                pass
    return {}


def _offers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("offers", "items", "results", "jobOffers"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        return _offers(data)
    return []


def _pick(d: dict[str, Any], *names, default=None):
    for name in names:
        value = d.get(name)
        if value not in (None, "", []):
            return value
    return default


def _company(value: Any) -> str | None:
    if isinstance(value, str):
        return norm_text(value)
    if isinstance(value, dict):
        return norm_text(str(_pick(value, "name", "employerName", "label", default=""))) or None
    return None


async def discover_offers(limit: int = 100000) -> list[dict[str, Any]]:
    async with streamablehttp_client(MCP_URL) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            discovered = []
            seen = set()
            page = 1
            while len(discovered) < limit:
                search = await session.call_tool(
                    "search_job_offers",
                    arguments={"filters": {"pageSize": 50, "pageNumber": page}},
                )
                rows = _offers(_payload(search))
                if not rows:
                    break
                before = len(discovered)
                for offer in rows:
                    sid = str(_pick(offer, "offerId", "id", "groupId", "groupID", default=""))
                    if not sid or sid in seen:
                        continue
                    seen.add(sid)
                    discovered.append(offer)
                    if len(discovered) >= limit:
                        break
                if len(discovered) == before:
                    break
                page += 1
            return discovered


def discover_offers_sync(limit: int = 100000):
    return asyncio.run(discover_offers(limit))


async def fetch_batch(limit: int = 50) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    async with streamablehttp_client(MCP_URL) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            discovered = []
            seen = set()
            page = 1
            while len(discovered) < limit:
                search = await session.call_tool(
                    "search_job_offers",
                    arguments={"filters": {"pageSize": 50, "pageNumber": page}},
                )
                rows = _offers(_payload(search))
                if not rows:
                    break
                before = len(discovered)
                for offer in rows:
                    sid = str(_pick(offer, "offerId", "id", "groupId", "groupID", default=""))
                    if not sid or sid in seen:
                        continue
                    seen.add(sid)
                    discovered.append(offer)
                    if len(discovered) >= limit:
                        break
                if len(discovered) == before:
                    break
                page += 1

            out = []
            for offer in discovered:
                gid = _pick(offer, "groupId", "groupID")
                if not gid:
                    continue
                details_result = await session.call_tool(
                    "get_job_offer_details",
                    arguments={"groupId": gid},
                )
                out.append((offer, _payload(details_result)))
            return out


async def fetch_groups(group_ids: list[str]) -> list[dict[str, Any]]:
    async with streamablehttp_client(MCP_URL) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            out = []
            for gid in group_ids:
                result = await session.call_tool(
                    "get_job_offer_details",
                    arguments={"groupId": gid},
                )
                out.append(_payload(result))
            return out


def fetch_batch_sync(limit: int = 50):
    return asyncio.run(fetch_batch(limit))


def fetch_groups_sync(group_ids: list[str]):
    return asyncio.run(fetch_groups(group_ids))


async def fetch_offers_by_ids(offer_ids: list[str], max_pages: int = 20):
    targets=set(str(x) for x in offer_ids)
    found={}
    async with streamablehttp_client(MCP_URL) as streams:
        read_stream, write_stream = streams[0], streams[1]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            for page in range(1,max_pages+1):
                search=await session.call_tool(
                    "search_job_offers",
                    arguments={"filters":{"pageSize":50,"pageNumber":page}},
                )
                rows=_offers(_payload(search))
                if not rows:
                    break
                for offer in rows:
                    oid=str(_pick(offer,"offerId","id",default=""))
                    if oid not in targets or oid in found:
                        continue
                    gid=_pick(offer,"groupId","groupID")
                    if not gid:
                        continue
                    details_result=await session.call_tool(
                        "get_job_offer_details",
                        arguments={"groupId":gid},
                    )
                    found[oid]=(offer,_payload(details_result))
                if targets <= set(found):
                    break
    return found


def fetch_offers_by_ids_sync(offer_ids: list[str], max_pages: int = 20):
    return asyncio.run(fetch_offers_by_ids(offer_ids,max_pages=max_pages))


def parse(search_row: dict[str, Any], details: dict[str, Any]) -> ParsedPosting:
    offer_id = str(_pick(search_row, "offerId", "id", default=""))
    group_id = str(_pick(search_row, "groupId", default=""))
    url = str(_pick(details, "offerUrl", "url", default=_pick(search_row, "url", "offerUrl", default="")))
    title = norm_text(str(_pick(details, "title", "jobTitle", default=_pick(search_row, "title", default=""))))
    company = _company(_pick(details, "company", "employer", "hiringOrganization")) or _company(
        _pick(search_row, "company", "employer", "employerName", "companyName")
    )
    if not offer_id:
        offer_id = group_id
    if not offer_id or not title:
        raise ValueError("MCP_CONTRACT_DRIFT: offerId/title missing")

    body = json.dumps(details, ensure_ascii=False, sort_keys=True)
    return ParsedPosting(
        source="theprotocol",
        source_posting_id=offer_id,
        url=url,
        title=title,
        company_mention=company,
        body_text=body,
        source_specific={
            "transport": "official-mcp",
            "groupId": group_id,
            "search": search_row,
            "details": details,
        },
    )
