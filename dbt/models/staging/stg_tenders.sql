select
    publication_number,
    publication_date,
    publication_date_raw,
    notice_type,

    title,
    title_language,

    description,
    description_language,

    lot_descriptions,
    lot_description_language,
    lot_description_text,

    buyer_name,
    buyer_name_language,
    buyer_countries,
    first_buyer_country,

    cpv_codes,
    first_cpv_code,

    procedure_type,
    contract_natures,

    deadlines,
    earliest_deadline,
    latest_deadline,

    estimated_value,
    estimated_value_currency,

    performance_countries,
    performance_regions,

    source_html_url,
    source_xml_url,

    ingestion_run_id,
    source,
    loaded_at

from {{ source('silver', 'tenders') }}
