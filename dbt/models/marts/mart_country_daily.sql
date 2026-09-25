with country_memberships as (

    select
        publication_number,
        publication_date,
        unnest(buyer_countries) as buyer_country

    from {{ ref('stg_tenders') }}

)

select
    publication_date,
    buyer_country,
    count(distinct publication_number) as tender_count

from country_memberships

group by
    publication_date,
    buyer_country
