-- Marketplace/Shopee evidence and refresh checkpoints for the Apify source.
-- Safe to run after the original scraper schema migration.
create table if not exists scraper.marketplace_products (
    platform text not null,
    product_id text not null,
    topic_id text not null references scraper.topics(id) on delete cascade,
    title text not null,
    description text not null default '',
    url text,
    shop_name text,
    category text,
    price double precision,
    original_price double precision,
    rating double precision,
    rating_count bigint,
    sold_count bigint,
    stock bigint,
    image_url text,
    query text,
    first_seen_at text not null,
    last_seen_at text not null,
    primary key (platform, product_id, topic_id)
);
create index if not exists idx_marketplace_products_topic
    on scraper.marketplace_products(topic_id, platform, last_seen_at desc);
create table if not exists scraper.marketplace_refreshes (
    topic_id text not null references scraper.topics(id) on delete cascade,
    platform text not null,
    refreshed_at text not null,
    primary key (topic_id, platform)
);
alter table scraper.marketplace_products enable row level security;
alter table scraper.marketplace_refreshes enable row level security;
