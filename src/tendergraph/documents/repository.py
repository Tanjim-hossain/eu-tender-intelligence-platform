from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from tendergraph.documents.models import (
    ProcurementDocumentReference,
    StoredProcurementDocument,
    TenderDocumentPackage,
)

PACKAGE_DISCLAIMER = (
    "TenderGraph only fetches URLs published in the official TED notice. "
    "Restricted or authenticated resources are not bypassed, and extracted text "
    "must still be verified against the buyer's original procurement documents."
)


@dataclass(frozen=True, slots=True)
class NoticeDocumentSource:
    publication_number: str
    title: str | None
    source_xml_url: str | None


@dataclass(frozen=True, slots=True)
class ExtractedDocumentText:
    document_id: str
    source_url: str
    text: str


class DocumentRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def get_notice_source(self, publication_number: str) -> NoticeDocumentSource | None:
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT publication_number, title, source_xml_url
                FROM silver.tenders
                WHERE publication_number = %(publication_number)s;
                """,
                {"publication_number": publication_number},
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return NoticeDocumentSource(
            publication_number=row[0],
            title=row[1],
            source_xml_url=row[2],
        )

    def replace_discovery(
        self,
        source: NoticeDocumentSource,
        references: list[ProcurementDocumentReference],
        *,
        xml_sha256: str,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO documents.packages (
                    publication_number, title, source_xml_url, package_status,
                    xml_sha256, error, discovered_at, updated_at
                ) VALUES (
                    %(publication_number)s, %(title)s, %(source_xml_url)s,
                    'ingested', %(xml_sha256)s, NULL, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (publication_number) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_xml_url = EXCLUDED.source_xml_url,
                    package_status = 'ingested',
                    xml_sha256 = EXCLUDED.xml_sha256,
                    error = NULL,
                    discovered_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                {
                    "publication_number": source.publication_number,
                    "title": source.title,
                    "source_xml_url": source.source_xml_url,
                    "xml_sha256": xml_sha256,
                },
            )
            connection.execute(
                "DELETE FROM documents.assets WHERE publication_number = %(publication_number)s;",
                {"publication_number": source.publication_number},
            )
            for reference in references:
                connection.execute(
                    """
                    INSERT INTO documents.assets (
                        publication_number, document_id, source_url, restricted,
                        restriction_code, official_languages, unofficial_languages,
                        status
                    ) VALUES (
                        %(publication_number)s, %(document_id)s, %(source_url)s,
                        %(restricted)s, %(restriction_code)s,
                        %(official_languages)s, %(unofficial_languages)s,
                        %(status)s
                    );
                    """,
                    {
                        "publication_number": source.publication_number,
                        "document_id": reference.document_id,
                        "source_url": str(reference.source_url),
                        "restricted": reference.restricted,
                        "restriction_code": reference.restriction_code,
                        "official_languages": reference.official_languages,
                        "unofficial_languages": reference.unofficial_languages,
                        "status": "restricted" if reference.restricted else "discovered",
                    },
                )

    def record_fetch(
        self,
        publication_number: str,
        document_id: str,
        *,
        status: str,
        final_url: str | None,
        content_type: str | None,
        byte_count: int | None,
        sha256: str | None,
        cache_path: str | None,
        extraction_method: str | None,
        extracted_text: str | None,
        error: str | None,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE documents.assets
                SET status = %(status)s,
                    final_url = %(final_url)s,
                    content_type = %(content_type)s,
                    byte_count = %(byte_count)s,
                    sha256 = %(sha256)s,
                    cache_path = %(cache_path)s,
                    extraction_method = %(extraction_method)s,
                    extracted_text = %(extracted_text)s,
                    error = %(error)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE publication_number = %(publication_number)s
                  AND document_id = %(document_id)s;
                """,
                {
                    "status": status,
                    "final_url": final_url,
                    "content_type": content_type,
                    "byte_count": byte_count,
                    "sha256": sha256,
                    "cache_path": cache_path,
                    "extraction_method": extraction_method,
                    "extracted_text": extracted_text,
                    "error": error,
                    "publication_number": publication_number,
                    "document_id": document_id,
                },
            )

    def set_package_status(
        self,
        publication_number: str,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE documents.packages
                SET package_status = %(status)s,
                    error = %(error)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE publication_number = %(publication_number)s;
                """,
                {"status": status, "error": error, "publication_number": publication_number},
            )

    def get_package(self, publication_number: str) -> TenderDocumentPackage | None:
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT title, source_xml_url, package_status, discovered_at,
                       updated_at, error
                FROM documents.packages
                WHERE publication_number = %(publication_number)s;
                """,
                {"publication_number": publication_number},
            )
            package_row = cursor.fetchone()
            if package_row is None:
                return None
            cursor.execute(
                """
                SELECT document_id, source_url, restricted, restriction_code,
                       official_languages, unofficial_languages, status, final_url,
                       content_type, byte_count, sha256, cache_path,
                       extraction_method, COALESCE(length(extracted_text), 0),
                       error, updated_at
                FROM documents.assets
                WHERE publication_number = %(publication_number)s
                ORDER BY document_id;
                """,
                {"publication_number": publication_number},
            )
            rows = cursor.fetchall()

        documents = [
            StoredProcurementDocument(
                document_id=row[0], source_url=row[1], restricted=row[2],
                restriction_code=row[3], official_languages=list(row[4] or []),
                unofficial_languages=list(row[5] or []), status=row[6],
                final_url=row[7], content_type=row[8], byte_count=row[9],
                sha256=row[10], cache_path=row[11], extraction_method=row[12],
                extracted_characters=row[13], error=row[14], updated_at=row[15],
            )
            for row in rows
        ]
        return TenderDocumentPackage(
            publication_number=publication_number,
            title=package_row[0],
            source_xml_url=package_row[1],
            package_status=package_row[2],
            documents=documents,
            extracted_document_count=sum(item.status == "extracted" for item in documents),
            restricted_document_count=sum(item.restricted for item in documents),
            failed_document_count=sum(item.status in {"failed", "access_denied"} for item in documents),
            discovered_at=package_row[3], updated_at=package_row[4], error=package_row[5],
            disclaimer=PACKAGE_DISCLAIMER,
        )

    def extracted_texts(self, publication_number: str) -> list[ExtractedDocumentText]:
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT document_id, source_url, extracted_text
                FROM documents.assets
                WHERE publication_number = %(publication_number)s
                  AND status = 'extracted'
                  AND extracted_text IS NOT NULL
                  AND extracted_text <> ''
                ORDER BY document_id;
                """,
                {"publication_number": publication_number},
            )
            rows = cursor.fetchall()
        return [ExtractedDocumentText(row[0], row[1], row[2]) for row in rows]
