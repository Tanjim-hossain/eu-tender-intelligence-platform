from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from tendergraph.documents.extract import extract_document_text
from tendergraph.documents.fetcher import DocumentFetchError, SafeDocumentFetcher
from tendergraph.documents.models import (
    DocumentPackageIntelligence,
    PackageRequirementSignal,
    PackageRisk,
    TenderDocumentPackage,
)
from tendergraph.documents.repository import DocumentRepository, NoticeDocumentSource
from tendergraph.documents.xml import parse_procurement_document_references
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
    "TenderGraph could safely fetch and convert to text. It is not a legal "
    "eligibility determination and may be incomplete when portals require "
    "authentication, JavaScript, registration, or unsupported file formats."
)


class TenderNotFoundError(LookupError):
    """Raised when a publication number does not exist in Silver."""


class TenderDocumentSourceUnavailable(RuntimeError):
    """Raised when an indexed tender has no official XML source URL."""


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
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
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

    def package(self, publication_number: str) -> TenderDocumentPackage:
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

    def _require_source(self, publication_number: str) -> NoticeDocumentSource:
        source = self._repository.get_notice_source(publication_number)
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

        existing = self._repository.get_package(publication_number)
        if existing is not None and not force:
            pending = [
                item
                for item in existing.documents
                if not item.restricted and item.status == "discovered"
            ]
            if not fetch_documents or not pending:
                return existing
        else:
            xml_result = self._fetcher.fetch(
                source.source_xml_url,
                max_bytes=XML_MAX_BYTES,
            )
            references = parse_procurement_document_references(xml_result.content)
            self._repository.replace_discovery(
                source,
                references[:MAX_DOCUMENTS_PER_PACKAGE],
                xml_sha256=xml_result.sha256,
            )

        if fetch_documents:
            current = self._repository.get_package(publication_number)
            if current is None:
                raise RuntimeError("Document package disappeared after discovery")
            for document in current.documents:
                if document.restricted or document.status not in {"discovered", "failed"}:
                    continue
                self._fetch_document(publication_number, document.document_id, document.source_url)
            self._update_package_status(publication_number)

        package = self._repository.get_package(publication_number)
        if package is None:
            raise RuntimeError("Document package unavailable after ingestion")
        return package

    def _fetch_document(self, publication_number: str, document_id: str, source_url: str) -> None:
        try:
            result = self._fetcher.fetch(source_url, max_bytes=DOCUMENT_MAX_BYTES)
            extraction = extract_document_text(
                result.content,
                content_type=result.content_type,
                source_url=result.final_url,
            )
            folder = self._cache_root / _safe_segment(publication_number)
            folder.mkdir(parents=True, exist_ok=True)
            filename = sha256(source_url.encode("utf-8")).hexdigest()[:20]
            path = folder / f"{filename}{_cache_suffix(result.content_type, result.final_url)}"
            path.write_bytes(result.content)

            text = extraction.text or None
            status = "extracted" if text else ("unsupported" if not extraction.supported else "fetched")
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
        except DocumentFetchError as exc:
            message = str(exc)
            status = "access_denied" if "access denied" in message.casefold() else "failed"
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

    def _update_package_status(self, publication_number: str) -> None:
        package = self._repository.get_package(publication_number)
        if package is None:
            return
        if package.documents and all(item.restricted for item in package.documents):
            status = "restricted_only"
        elif any(item.status in {"failed", "access_denied", "unsupported"} for item in package.documents):
            status = "partial"
        else:
            status = "ingested"
        self._repository.set_package_status(publication_number, status)

    def intelligence(self, publication_number: str) -> DocumentPackageIntelligence:
        package = self.package(publication_number)
        texts = self._repository.extracted_texts(publication_number)
        requirements: list[PackageRequirementSignal] = []

        for rule in REQUIREMENT_RULES:
            for document in texts:
                match = _find_phrase(document.text, rule.phrases)
                if match is None:
                    continue
                start, end = match
                explicit = _is_explicit_requirement(document.text, start, end)
                requirements.append(
                    PackageRequirementSignal(
                        key=rule.key,
                        category=rule.category,
                        label=rule.label,
                        evidence_strength="explicit" if explicit else "mentioned",
                        evidence=_snippet(document.text, start, end),
                        document_id=document.document_id,
                        source_url=document.source_url,
                        hard_gate=rule.hard_gate and explicit,
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
                        f"{package.restricted_document_count} procurement document(s) "
                        "have restricted or controlled access and were not fetched."
                    ),
                )
            )
        unsupported = sum(
            item.status in {"unsupported", "failed", "access_denied"}
            for item in package.documents
        )
        if unsupported:
            risks.append(
                PackageRisk(
                    key="unread_documents",
                    severity="medium",
                    message=f"{unsupported} document(s) could not be converted into reviewable text.",
                )
            )
        for item in requirements:
            if item.hard_gate:
                risks.append(
                    PackageRisk(
                        key=f"hard_gate_{item.key}",
                        severity="high" if item.category == "security" else "medium",
                        message=f"Explicit potential hard gate detected in procurement document: {item.label}.",
                        document_id=item.document_id,
                    )
                )

        total_chars = sum(len(item.text) for item in texts)
        if not texts:
            coverage = "none"
        elif unsupported or package.restricted_document_count:
            coverage = "partial"
        elif total_chars >= 1000:
            coverage = "substantive"
        else:
            coverage = "partial"

        actions = [
            "Verify extracted requirements against the original buyer documents before a bid/no-bid decision."
        ]
        if package.package_status == "not_ingested":
            actions.insert(0, "Ingest the procurement-document package before relying on package intelligence.")
        if package.restricted_document_count:
            actions.append("Open restricted-access document links manually and complete any buyer-required access process.")
        if unsupported:
            actions.append("Review unread or unsupported documents manually; they can contain mandatory criteria.")
        if any(item.hard_gate for item in requirements):
            actions.append("Confirm every explicit potential hard gate with the bid team and documentary evidence.")

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
