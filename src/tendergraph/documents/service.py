from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from tendergraph.documents.extract import extract_document_text
from tendergraph.documents.fetcher import (
    DocumentFetchError,
    SafeDocumentFetcher,
    UnsafeDocumentUrlError,
)
from tendergraph.documents.models import (
    DocumentPackageIntelligence,
    DocumentProvenance,
    DocumentProvenanceChunk,
    PackageCoverage,
    PackageRequirementSignal,
    PackageRisk,
    TenderDocumentPackage,
)
from tendergraph.documents.repository import (
    DocumentRepository,
    NoticeDocumentSource,
)
from tendergraph.documents.xml import (
    parse_procurement_document_references,
)
from tendergraph.qualification.service import (
    REQUIREMENT_RULES,
    _find_phrase,
    _is_explicit_requirement,
    _snippet,
)

XML_MAX_BYTES = 8_000_000
DOCUMENT_MAX_BYTES = 20_000_000
MAX_DOCUMENTS_PER_PACKAGE = 20
PACKAGE_INTELLIGENCE_DISCLAIMER = (
    "Package intelligence is deterministic evidence extraction over documents "
    "TenderGraph could safely fetch and convert to text. Page and section "
    "provenance is shown when the source format exposes it. This is not a legal "
    "eligibility determination and may be incomplete when portals require "
    "authentication, JavaScript, registration, or unsupported file formats."
)
PROVENANCE_DISCLAIMER = (
    "Provenance chunks are deterministic local extraction artifacts, not buyer-"
    "issued citations. Page numbers are derived from PDF page boundaries and "
    "sections from supported document headings; verify the original document."
)


class TenderNotFoundError(LookupError):
    """Raised when a publication number does not exist in Silver."""


class TenderDocumentSourceUnavailable(RuntimeError):
    """Raised when an indexed tender has no official XML source URL."""


@dataclass(frozen=True, slots=True)
class _EvidenceUnit:
    document_id: str
    source_url: str
    text: str
    chunk_id: str | None
    page_number: int | None
    section_title: str | None


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned or "document"


def _cache_suffix(content_type: str | None, url: str) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().casefold()
    by_mime = {
        "application/pdf": ".pdf",
        "text/html": ".html",
        "application/xhtml+xml": ".html",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "application/json": ".json",
        "text/plain": ".txt",
        "text/csv": ".csv",
        (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ): ".docx",
    }
    if mime in by_mime:
        return by_mime[mime]
    suffix = Path(urlparse(url).path).suffix
    return suffix[:12] if suffix else ".bin"


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        *,
        fetcher: SafeDocumentFetcher | None = None,
        cache_root: Path = Path("data/documents"),
    ) -> None:
        self._repository = repository
        self._fetcher = fetcher or SafeDocumentFetcher()
        self._cache_root = cache_root

    def package(
        self,
        publication_number: str,
    ) -> TenderDocumentPackage:
        stored = self._repository.get_package(publication_number)
        if stored is not None:
            return stored

        source = self._require_source(publication_number)
        return TenderDocumentPackage(
            publication_number=source.publication_number,
            title=source.title,
            source_xml_url=source.source_xml_url,
            package_status="not_ingested",
            documents=[],
            extracted_document_count=0,
            restricted_document_count=0,
            failed_document_count=0,
            disclaimer=(
                "No procurement-document package has been ingested yet. "
                "Ingestion uses only links published by the official TED notice."
            ),
        )

    def provenance(
        self,
        publication_number: str,
    ) -> DocumentProvenance:
        self._require_source(publication_number)
        chunks = self._repository.provenance_chunks(
            publication_number
        )
        return DocumentProvenance(
            publication_number=publication_number,
            chunk_count=len(chunks),
            documents_with_chunks=len(
                {chunk.document_id for chunk in chunks}
            ),
            chunks=chunks,
            disclaimer=PROVENANCE_DISCLAIMER,
        )

    def _require_source(
        self,
        publication_number: str,
    ) -> NoticeDocumentSource:
        source = self._repository.get_notice_source(
            publication_number
        )
        if source is None:
            raise TenderNotFoundError(publication_number)
        return source

    def ingest(
        self,
        publication_number: str,
        *,
        fetch_documents: bool = True,
        force: bool = False,
    ) -> TenderDocumentPackage:
        source = self._require_source(publication_number)
        if not source.source_xml_url:
            raise TenderDocumentSourceUnavailable(
                "The indexed TED record has no XML source URL"
            )

        existing = self._repository.get_package(
            publication_number
        )
        if existing is not None and not force:
            pending = [
                item
                for item in existing.documents
                if (
                    not item.restricted
                    and (
                        item.status in {"discovered", "failed"}
                        or (
                            item.status == "extracted"
                            and item.chunk_count == 0
                        )
                    )
                )
            ]
            if not fetch_documents or not pending:
                return existing
        else:
            xml_result = self._fetcher.fetch(
                source.source_xml_url,
                max_bytes=XML_MAX_BYTES,
            )
            references = parse_procurement_document_references(
                xml_result.content
            )
            self._repository.replace_discovery(
                source,
                references[:MAX_DOCUMENTS_PER_PACKAGE],
                xml_sha256=xml_result.sha256,
            )

        if fetch_documents:
            current = self._repository.get_package(
                publication_number
            )
            if current is None:
                raise RuntimeError(
                    "Document package disappeared after discovery"
                )
            for document in current.documents:
                should_fetch = (
                    not document.restricted
                    and (
                        document.status in {"discovered", "failed"}
                        or (
                            document.status == "extracted"
                            and document.chunk_count == 0
                        )
                    )
                )
                if not should_fetch:
                    continue
                self._fetch_document(
                    publication_number,
                    document.document_id,
                    document.source_url,
                )
            self._update_package_status(publication_number)

        package = self._repository.get_package(
            publication_number
        )
        if package is None:
            raise RuntimeError(
                "Document package unavailable after ingestion"
            )
        return package

    def _fetch_document(
        self,
        publication_number: str,
        document_id: str,
        source_url: str,
    ) -> None:
        try:
            result = self._fetcher.fetch(
                source_url,
                max_bytes=DOCUMENT_MAX_BYTES,
            )
            extraction = extract_document_text(
                result.content,
                content_type=result.content_type,
                source_url=result.final_url,
            )
            folder = (
                self._cache_root
                / _safe_segment(publication_number)
            )
            folder.mkdir(parents=True, exist_ok=True)
            filename = sha256(
                source_url.encode("utf-8")
            ).hexdigest()[:20]
            path = folder / (
                f"{filename}"
                f"{_cache_suffix(result.content_type, result.final_url)}"
            )
            path.write_bytes(result.content)

            text = extraction.text or None
            status = (
                "extracted"
                if text
                else (
                    "unsupported"
                    if not extraction.supported
                    else "fetched"
                )
            )
            self._repository.record_fetch(
                publication_number,
                document_id,
                status=status,
                final_url=result.final_url,
                content_type=result.content_type,
                byte_count=result.byte_count,
                sha256=result.sha256,
                cache_path=str(path),
                extraction_method=extraction.method,
                extracted_text=text,
                error=None,
            )

            provenance_chunks = [
                DocumentProvenanceChunk(
                    document_id=document_id,
                    source_url=source_url,
                    chunk_id=(
                        f"{_safe_segment(document_id)}:"
                        f"{chunk.chunk_index:04d}"
                    ),
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    text=chunk.text,
                    character_count=chunk.character_count,
                    checksum=chunk.checksum,
                )
                for chunk in extraction.chunks
            ]
            self._repository.replace_chunks(
                publication_number,
                document_id,
                provenance_chunks,
            )
        except (
            DocumentFetchError,
            UnsafeDocumentUrlError,
        ) as exc:
            message = str(exc)
            status = (
                "access_denied"
                if "access denied" in message.casefold()
                else "failed"
            )
            self._repository.record_fetch(
                publication_number,
                document_id,
                status=status,
                final_url=None,
                content_type=None,
                byte_count=None,
                sha256=None,
                cache_path=None,
                extraction_method=None,
                extracted_text=None,
                error=message,
            )
            self._repository.replace_chunks(
                publication_number,
                document_id,
                [],
            )

    def _update_package_status(
        self,
        publication_number: str,
    ) -> None:
        package = self._repository.get_package(
            publication_number
        )
        if package is None:
            return
        if package.documents and all(
            item.restricted
            for item in package.documents
        ):
            status = "restricted_only"
        elif any(
            item.status
            in {"failed", "access_denied", "unsupported"}
            for item in package.documents
        ):
            status = "partial"
        else:
            status = "ingested"
        self._repository.set_package_status(
            publication_number,
            status,
        )

    def _evidence_units(
        self,
        publication_number: str,
    ) -> list[_EvidenceUnit]:
        chunks = self._repository.provenance_chunks(
            publication_number
        )
        units = [
            _EvidenceUnit(
                document_id=chunk.document_id,
                source_url=chunk.source_url,
                text=chunk.text,
                chunk_id=chunk.chunk_id,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
            )
            for chunk in chunks
        ]
        chunked_document_ids = {
            chunk.document_id for chunk in chunks
        }

        for document in self._repository.extracted_texts(
            publication_number
        ):
            if document.document_id in chunked_document_ids:
                continue
            units.append(
                _EvidenceUnit(
                    document_id=document.document_id,
                    source_url=document.source_url,
                    text=document.text,
                    chunk_id=None,
                    page_number=None,
                    section_title=None,
                )
            )
        return units

    def intelligence(
        self,
        publication_number: str,
    ) -> DocumentPackageIntelligence:
        package = self.package(publication_number)
        texts = self._repository.extracted_texts(
            publication_number
        )
        evidence_units = self._evidence_units(
            publication_number
        )
        requirements: list[PackageRequirementSignal] = []

        for rule in REQUIREMENT_RULES:
            for unit in evidence_units:
                match = _find_phrase(
                    unit.text,
                    rule.phrases,
                )
                if match is None:
                    continue
                start, end = match
                explicit = _is_explicit_requirement(
                    unit.text,
                    start,
                    end,
                )
                requirements.append(
                    PackageRequirementSignal(
                        key=rule.key,
                        category=rule.category,
                        label=rule.label,
                        evidence_strength=(
                            "explicit"
                            if explicit
                            else "mentioned"
                        ),
                        evidence=_snippet(
                            unit.text,
                            start,
                            end,
                        ),
                        document_id=unit.document_id,
                        source_url=unit.source_url,
                        chunk_id=unit.chunk_id,
                        page_number=unit.page_number,
                        section_title=unit.section_title,
                        hard_gate=(
                            rule.hard_gate and explicit
                        ),
                    )
                )
                break

        risks: list[PackageRisk] = []
        if package.restricted_document_count:
            risks.append(
                PackageRisk(
                    key="restricted_documents",
                    severity="medium",
                    message=(
                        f"{package.restricted_document_count} "
                        "procurement document(s) have restricted or "
                        "controlled access and were not fetched."
                    ),
                )
            )
        unsupported = sum(
            item.status
            in {"unsupported", "failed", "access_denied"}
            for item in package.documents
        )
        if unsupported:
            risks.append(
                PackageRisk(
                    key="unread_documents",
                    severity="medium",
                    message=(
                        f"{unsupported} document(s) could not be "
                        "converted into reviewable text."
                    ),
                )
            )
        for item in requirements:
            if item.hard_gate:
                risks.append(
                    PackageRisk(
                        key=f"hard_gate_{item.key}",
                        severity=(
                            "high"
                            if item.category == "security"
                            else "medium"
                        ),
                        message=(
                            "Explicit potential hard gate detected in "
                            f"procurement document: {item.label}."
                        ),
                        document_id=item.document_id,
                    )
                )

        total_chars = sum(
            len(item.text)
            for item in texts
        )
        coverage: PackageCoverage
        if not texts:
            coverage = "none"
        elif (
            unsupported
            or package.restricted_document_count
        ):
            coverage = "partial"
        elif total_chars >= 1000:
            coverage = "substantive"
        else:
            coverage = "partial"

        actions = [
            (
                "Verify extracted requirements against the original buyer "
                "documents before a bid/no-bid decision."
            )
        ]
        if package.package_status == "not_ingested":
            actions.insert(
                0,
                "Ingest the procurement-document package before relying "
                "on package intelligence.",
            )
        if package.restricted_document_count:
            actions.append(
                "Open restricted-access document links manually and complete "
                "any buyer-required access process."
            )
        if unsupported:
            actions.append(
                "Review unread or unsupported documents manually; they can "
                "contain mandatory criteria."
            )
        if any(
            item.hard_gate
            for item in requirements
        ):
            actions.append(
                "Confirm every explicit potential hard gate with the bid "
                "team and documentary evidence."
            )

        return DocumentPackageIntelligence(
            publication_number=publication_number,
            package_status=package.package_status,
            coverage=coverage,
            documents_considered=len(texts),
            total_extracted_characters=total_chars,
            requirements=requirements,
            risks=risks,
            next_actions=actions[:8],
            disclaimer=PACKAGE_INTELLIGENCE_DISCLAIMER,
        )
