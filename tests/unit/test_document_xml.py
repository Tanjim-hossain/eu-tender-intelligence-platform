from tendergraph.documents.xml import parse_procurement_document_references


def test_parse_procurement_document_references() -> None:
    xml = b"""<?xml version='1.0' encoding='UTF-8'?>
    <ContractNotice xmlns:cac='urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
                    xmlns:cbc='urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
                    xmlns:ext='urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
                    xmlns:efext='http://data.europa.eu/p27/eforms-ubl-extensions/1'
                    xmlns:efac='http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1'>
      <cac:ProcurementProjectLot>
        <cac:TenderingTerms>
          <cac:CallForTendersDocumentReference>
            <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionContent>
              <efext:EformsExtension>
                <efac:OfficialLanguages><cac:Language><cbc:ID>ENG</cbc:ID></cac:Language></efac:OfficialLanguages>
              </efext:EformsExtension>
            </ext:ExtensionContent></ext:UBLExtension></ext:UBLExtensions>
            <cbc:ID>specification</cbc:ID>
            <cbc:DocumentType>non-restricted-document</cbc:DocumentType>
            <cac:Attachment><cac:ExternalReference><cbc:URI>https://buyer.example/spec.pdf</cbc:URI></cac:ExternalReference></cac:Attachment>
          </cac:CallForTendersDocumentReference>
          <cac:CallForTendersDocumentReference>
            <cbc:ID>controlled</cbc:ID>
            <cbc:DocumentTypeCode listName='communication-justification'>ipr-iss</cbc:DocumentTypeCode>
            <cbc:DocumentType>restricted-document</cbc:DocumentType>
            <cac:Attachment><cac:ExternalReference><cbc:URI>https://buyer.example/access</cbc:URI></cac:ExternalReference></cac:Attachment>
          </cac:CallForTendersDocumentReference>
        </cac:TenderingTerms>
      </cac:ProcurementProjectLot>
    </ContractNotice>"""

    references = parse_procurement_document_references(xml)

    assert len(references) == 2
    assert references[0].document_id == "specification"
    assert str(references[0].source_url) == "https://buyer.example/spec.pdf"
    assert references[0].official_languages == ["ENG"]
    assert references[0].restricted is False
    assert references[1].restricted is True
    assert references[1].restriction_code == "ipr-iss"


def test_duplicate_reference_ids_are_disambiguated() -> None:
    xml = b"""<Notice xmlns:cac='x' xmlns:cbc='y'>
    <cac:CallForTendersDocumentReference><cbc:ID>DOC</cbc:ID><cac:Attachment><cac:ExternalReference><cbc:URI>https://example.org/a</cbc:URI></cac:ExternalReference></cac:Attachment></cac:CallForTendersDocumentReference>
    <cac:CallForTendersDocumentReference><cbc:ID>DOC</cbc:ID><cac:Attachment><cac:ExternalReference><cbc:URI>https://example.org/b</cbc:URI></cac:ExternalReference></cac:Attachment></cac:CallForTendersDocumentReference>
    </Notice>"""

    references = parse_procurement_document_references(xml)

    assert [item.document_id for item in references] == ["DOC", "DOC-2"]
