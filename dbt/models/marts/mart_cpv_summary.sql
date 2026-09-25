with tender_cpv as (

    select distinct
        publication_number,
        publication_date,
        unnest(cpv_codes) as cpv_code

    from {{ ref('stg_tenders') }}

),

country_memberships as (

    select distinct
        publication_number,
        unnest(buyer_countries) as buyer_country

    from {{ ref('stg_tenders') }}

),

joined as (

    select
        tender_cpv.publication_number,
        tender_cpv.publication_date,
        tender_cpv.cpv_code,
        country_memberships.buyer_country

    from tender_cpv

    left join country_memberships
        using (publication_number)

)

select
    cpv_code,
    count(distinct publication_number) as tender_count,
    count(distinct buyer_country) as buyer_country_count,
    min(publication_date) as first_seen_date,
    max(publication_date) as last_seen_date

from joined

group by cpv_code
