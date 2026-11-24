"""Historical notice and explicit award evidence, scoped to the loaded index."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout
from pydantic import BaseModel

AWARD_TYPES = ("can-standard", "can-social", "can-tran", "can-desg")
CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS history"
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS history.award_evidence (
    publication_number TEXT PRIMARY KEY REFERENCES silver.tenders(publication_number)
        ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    winners JSONB NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
DISCLAIMER = (
    "Only indexed notices before this notice's publication date are included. "
    "Buyer matching uses normalized name and first country, not a verified entity ID. "
    "Result notices are not necessarily successful awards. Estimated values are not "
    "award prices. Named suppliers are historical contract-linked evidence, not "
    "confirmed current incumbents. Missing evidence is not evidence of absence."
)


class AwardSupplier(BaseModel):
    contract_id: str
    tender_id: str
    organization_id: str
    name: str


class HistoricalNotice(BaseModel):
    publication_number: str
    publication_date: date
    notice_type: str
    title: str
    estimated_value: Decimal | None
    currency: str | None
    source_url: str
    award_evidence_indexed: bool
    suppliers: list[AwardSupplier]


class ValueSummary(BaseModel):
    currency: str
    known_values: int
    median_estimated_value: Decimal


class BuyerHistory(BaseModel):
    publication_number: str
    buyer_name: str | None
    buyer_country: str
    window_start: date
    window_end_exclusive: date
    notice_count: int
    result_notice_count: int
    values: list[ValueSummary]
    notices: list[HistoricalNotice]
    disclaimer: str = DISCLAIMER


def _value(node: ET.Element, path: str) -> str:
    return (node.findtext(path) or "").strip()


def _unique_nodes(nodes: list[ET.Element], path: str) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    ambiguous: set[str] = set()
    for node in nodes:
        key = _value(node, path)
        if key in result:
            ambiguous.add(key)
        elif key:
            result[key] = node
    return {key: node for key, node in result.items() if key not in ambiguous}


def extract_award_suppliers(content: bytes) -> list[AwardSupplier]:
    """Follow explicit settled contract -> tender -> party -> organization references."""
    root = ET.fromstring(content)
    if root.tag.rsplit("}", 1)[-1] != "ContractAwardNotice":
        return []
    results = root.findall(".//{*}NoticeResult")
    if len(results) != 1:
        return []
    result = results[0]
    organizations = _unique_nodes(
        root.findall(".//{*}Organizations/{*}Organization"),
        "{*}Company/{*}PartyIdentification/{*}ID",
    )
    tenders = _unique_nodes(result.findall("{*}LotTender"), "{*}ID")
    parties = _unique_nodes(result.findall("{*}TenderingParty"), "{*}ID")
    contracts = _unique_nodes(result.findall("{*}SettledContract"), "{*}ID")
    suppliers: dict[tuple[str, str, str], AwardSupplier] = {}
    for contract_id, contract in contracts.items():
        for reference in contract.findall("{*}LotTender"):
            tender_id = _value(reference, "{*}ID")
            tender = tenders.get(tender_id)
            if tender is None or _value(tender, "{*}RankCode") == "0":
                continue
            party = parties.get(_value(tender, "{*}TenderingParty/{*}ID"))
            if party is None:
                continue
            for tenderer in party.findall("{*}Tenderer"):
                organization_id = _value(tenderer, "{*}ID")
                organization = organizations.get(organization_id)
                if organization is None:
                    continue
                # Do not expose explicitly identified natural persons or contact details.
                if _value(organization, "{*}NaturalPersonIndicator").lower() != "false":
                    continue
                name = _value(organization, "{*}Company/{*}PartyName/{*}Name")
                if name:
                    suppliers[(contract_id, tender_id, organization_id)] = AwardSupplier(
                        contract_id=contract_id, tender_id=tender_id,
                        organization_id=organization_id, name=name,
                    )
    return [suppliers[key] for key in sorted(suppliers)]


def ensure_history_schema(pool: ConnectionPool) -> None:
    with pool.connection() as connection:
        connection.execute(CREATE_SCHEMA)
        connection.execute(CREATE_TABLE)


MATCHED = """
WITH anchor AS (
    SELECT buyer_name, first_buyer_country, publication_date
    FROM silver.tenders WHERE publication_number = %(publication)s
), matched AS (
    SELECT t.*
    FROM silver.tenders AS t CROSS JOIN anchor AS a
    WHERE a.buyer_name IS NOT NULL AND btrim(a.buyer_name) <> ''
      AND lower(btrim(t.buyer_name)) = lower(btrim(a.buyer_name))
      AND t.first_buyer_country = a.first_buyer_country
      AND t.publication_date >= a.publication_date - %(days)s
      AND t.publication_date < a.publication_date
)
"""


def buyer_history(
    pool: ConnectionPool, publication: str, *, days: int = 365, limit: int = 20,
) -> BuyerHistory | None:
    params = {"publication": publication, "days": days, "limit": limit,
              "award_types": list(AWARD_TYPES)}
    with pool.connection() as connection:
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            anchor = connection.execute(
                """
                SELECT buyer_name, first_buyer_country, publication_date - %(days)s,
                       publication_date
                FROM silver.tenders WHERE publication_number = %(publication)s
                """, params,
            ).fetchone()
            if anchor is None:
                return None
            counts = connection.execute(
                MATCHED + """
                SELECT count(*), count(*) FILTER (WHERE notice_type = ANY(%(award_types)s))
                FROM matched
                """, params,
            ).fetchone()
            assert counts is not None
            values = connection.execute(
                MATCHED + """
                SELECT estimated_value_currency, count(*),
                       percentile_disc(0.5) WITHIN GROUP (ORDER BY estimated_value)
                FROM matched
                WHERE estimated_value IS NOT NULL AND estimated_value_currency IS NOT NULL
                GROUP BY estimated_value_currency ORDER BY estimated_value_currency
                """, params,
            ).fetchall()
            rows = connection.execute(
                MATCHED + """
                SELECT m.publication_number, m.publication_date, m.notice_type, m.title,
                       m.estimated_value, m.estimated_value_currency, m.source_html_url,
                       e.publication_number IS NOT NULL, e.winners
                FROM matched AS m
                LEFT JOIN history.award_evidence AS e USING (publication_number)
                ORDER BY m.publication_date DESC, m.publication_number DESC LIMIT %(limit)s
                """, params,
            ).fetchall()
    return BuyerHistory(
        publication_number=publication, buyer_name=anchor[0], buyer_country=anchor[1],
        window_start=anchor[2], window_end_exclusive=anchor[3],
        notice_count=counts[0], result_notice_count=counts[1],
        values=[ValueSummary(currency=v[0], known_values=v[1], median_estimated_value=v[2])
                for v in values],
        notices=[
            HistoricalNotice(
                publication_number=r[0], publication_date=r[1], notice_type=r[2],
                title=r[3], estimated_value=r[4], currency=r[5], source_url=r[6],
                award_evidence_indexed=r[7],
                suppliers=[AwardSupplier.model_validate(w) for w in (r[8] or [])],
            )
            for r in rows
        ],
    )


router = APIRouter(prefix="/history", tags=["history"])


@router.get("/{publication_number}", response_model=BuyerHistory)
def get_buyer_history(
    publication_number: str, request: Request,
    days: int = Query(365, ge=1, le=730), limit: int = Query(20, ge=1, le=50),
) -> BuyerHistory:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        typed_pool = cast(ConnectionPool, pool)
        ensure_history_schema(typed_pool)
        history = buyer_history(typed_pool, publication_number, days=days, limit=limit)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if history is None:
        raise HTTPException(status_code=404, detail="Tender not found")
    return history
