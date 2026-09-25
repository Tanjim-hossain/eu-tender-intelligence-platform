with buyer_country_memberships as (

    select
        publication_number,
        publication_date,
        buyer_name,
        unnest(buyer_countries) as buyer_country

    from {{ ref('stg_tenders') }}

    where buyer_name is not null

)

select
    buyer_name,
    count(distinct publication_number) as tender_count,
    count(distinct buyer_country) as buyer_country_count,
    min(publication_date) as first_seen_date,
    max(publication_date) as last_seen_date

from buyer_country_memberships

group by buyer_name
