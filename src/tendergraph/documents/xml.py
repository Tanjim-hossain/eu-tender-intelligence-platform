from __future__ import annotations

from collections.abc import Iterable
from xml.etree import ElementTree as ET

from tendergraph.documents.models import ProcurementDocumentReference


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_text(element: ET.Element, name: str) -> str | None:
    for child in element:
        if _local_name(child.tag) == name and child.text:
            value = child.text.strip()
            if value:
                return value
    return None


def _descendant_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text:
            value = child.text.strip()
            if value:
                return value
    return None


def _language_ids(element: ET.Element, container_name: str) -> list[str]:
    values: list[str] = []
    for container in element.iter():
        if _local_name(container.tag) != container_name:
            continue
        for descendant in container.iter():
            if _local_name(descendant.tag) != "ID" or not descendant.text:
                continue
            value = descendant.text.strip().upper()
            if value and value not in values:
                values.append(value)
    return values


def _reference_elements(root: ET.Element) -> Iterable[ET.Element]:
    for element in root.iter():
        if _local_name(element.tag) == "CallForTendersDocumentReference":
            yield element


def parse_procurement_document_references(
    xml_bytes: bytes,
) -> list[ProcurementDocumentReference]:
    """Extract BT-15/BT-615 procurement-document references from eForms XML."""

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("Invalid TED notice XML") from exc

    references: list[ProcurementDocumentReference] = []
    used_ids: set[str] = set()

    for index, element in enumerate(_reference_elements(root), start=1):
        source_url = _descendant_text(element, "URI")
        if not source_url:
            continue

        base_id = _direct_text(element, "ID") or f"DOC-{index:04d}"
        document_id = base_id
        suffix = 2
        while document_id in used_ids:
            document_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(document_id)

        document_type = (_direct_text(element, "DocumentType") or "").casefold()
        restricted = document_type == "restricted-document"

        references.append(
            ProcurementDocumentReference(
                document_id=document_id,
                source_url=source_url,
                restricted=restricted,
                restriction_code=_direct_text(element, "DocumentTypeCode"),
                official_languages=_language_ids(element, "OfficialLanguages"),
                unofficial_languages=_language_ids(element, "NonOfficialLanguages"),
            )
        )

    return references
