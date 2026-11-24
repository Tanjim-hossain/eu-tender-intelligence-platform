from tendergraph.history import extract_award_suppliers


def test_only_contract_linked_organization_is_reported() -> None:
    xml = b"""<ContractAwardNotice>
    <Organizations>
      <Organization><NaturalPersonIndicator>false</NaturalPersonIndicator><Company>
        <PartyIdentification><ID>ORG-1</ID></PartyIdentification>
        <PartyName><Name>Winning Company</Name></PartyName></Company></Organization>
      <Organization><NaturalPersonIndicator>false</NaturalPersonIndicator><Company>
        <PartyIdentification><ID>ORG-2</ID></PartyIdentification>
        <PartyName><Name>Unsuccessful Company</Name></PartyName></Company></Organization>
    </Organizations>
    <NoticeResult>
      <TenderingParty><ID>TPA-1</ID><Tenderer><ID>ORG-1</ID></Tenderer></TenderingParty>
      <TenderingParty><ID>TPA-2</ID><Tenderer><ID>ORG-2</ID></Tenderer></TenderingParty>
      <LotTender><ID>TEN-1</ID><TenderingParty><ID>TPA-1</ID></TenderingParty></LotTender>
      <LotTender><ID>TEN-2</ID><TenderingParty><ID>TPA-2</ID></TenderingParty></LotTender>
      <SettledContract><ID>CON-1</ID><LotTender><ID>TEN-1</ID></LotTender></SettledContract>
    </NoticeResult></ContractAwardNotice>"""
    suppliers = extract_award_suppliers(xml)
    assert len(suppliers) == 1
    assert suppliers[0].name == "Winning Company"
    assert suppliers[0].contract_id == "CON-1"
    assert extract_award_suppliers(xml.replace(b"false", b"true")) == []
    assert extract_award_suppliers(xml.replace(b"TEN-1</ID></LotTender>", b"missing</ID></LotTender>")) == []


def test_non_award_xml_is_not_supplier_evidence() -> None:
    assert extract_award_suppliers(b"<ContractNotice/>") == []
