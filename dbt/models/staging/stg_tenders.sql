select
    publication_number,
    publication_date,
    publication_date_raw,
    notice_type,

    title,
    title_language,

    buyer_name,
    buyer_name_language,

    buyer_countries,
    first_buyer_country,

    cpv_codes,
    first_cpv_code,

    source_html_url,
    source_xml_url,

    ingestion_run_id,
    source,
    loaded_at

from {{ source('silver', 'tenders') }}
