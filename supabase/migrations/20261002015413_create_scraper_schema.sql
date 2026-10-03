create schema if not exists scraper;
revoke all on schema scraper from public, anon, authenticated;

create table if not exists scraper.topics (
    id text primary key,
    name text not null,
    category text not null default 'umum',
    keywords text not null,
    product_terms text not null default '[]',
    exclude_terms text not null default '[]',
    cities text not null,
    own_place_id text,
    status text not null default 'discovering',
    is_seed smallint not null default 0 check (is_seed in (0, 1)),
    is_active smallint not null default 1 check (is_active in (0, 1)),
    created_at text not null,
    yt_last_discovery_at text,
    maps_last_refresh_at text
);

create table if not exists scraper.videos (
    video_id text not null,
    topic_id text not null references scraper.topics(id) on delete cascade,
    title text not null,
    channel_id text not null,
    channel_title text not null,
    description text not null default '',
    published_at text not null,
    discovered_at text not null,
    discovery_source text not null,
    content_type text not null default 'lainnya',
    is_active smallint not null default 1 check (is_active in (0, 1)),
    primary key (video_id, topic_id)
);
create index if not exists idx_videos_topic
    on scraper.videos(topic_id, is_active, published_at desc);

create table if not exists scraper.video_stats (
    video_id text not null,
    captured_at text not null,
    views bigint not null check (views >= 0),
    likes bigint,
    comments bigint,
    primary key (video_id, captured_at)
);
create index if not exists idx_video_stats_time
    on scraper.video_stats(captured_at);

create table if not exists scraper.places (
    place_id text not null,
    topic_id text not null references scraper.topics(id) on delete cascade,
    city text not null,
    is_relevant smallint not null default 1 check (is_relevant in (0, 1)),
    is_own smallint not null default 0 check (is_own in (0, 1)),
    first_seen_at text not null,
    last_seen_at text not null,
    primary key (place_id, topic_id)
);

create table if not exists scraper.place_snapshots (
    place_id text not null,
    topic_id text not null,
    captured_at text not null,
    name text not null,
    address text,
    maps_uri text,
    primary_type text,
    business_status text,
    rating double precision,
    user_rating_count bigint,
    name_mentions_product smallint not null default 0 check (name_mentions_product in (0, 1)),
    primary key (place_id, topic_id, captured_at)
);

create table if not exists scraper.comments (
    id text not null,
    topic_id text references scraper.topics(id) on delete cascade,
    product_id text,
    source text not null,
    place_id text,
    text text not null,
    text_is_translated smallint not null default 0 check (text_is_translated in (0, 1)),
    stars smallint check (stars between 1 and 5),
    author_name text,
    author_uri text,
    author_hash text,
    url text,
    created_at text not null,
    collected_at text not null,
    mentions_product smallint not null default 0 check (mentions_product in (0, 1)),
    status text not null default 'pending',
    category text,
    sentiment text,
    score double precision check (score between -1 and 1),
    aspects text not null default '[]',
    topics text not null default '[]',
    analyzer text,
    attempts integer not null default 0 check (attempts >= 0),
    expires_at text
);
create unique index if not exists idx_comments_topic_id
    on scraper.comments(topic_id, id) where topic_id is not null;
create unique index if not exists idx_comments_legacy_id
    on scraper.comments(id) where topic_id is null;
create index if not exists idx_comments_feed
    on scraper.comments(topic_id, created_at desc, id desc);
create index if not exists idx_comments_pending
    on scraper.comments(status, collected_at);

create table if not exists scraper.summaries (
    topic_id text primary key references scraper.topics(id) on delete cascade,
    payload text not null,
    analyzer text not null,
    generated_at text not null
);

create table if not exists scraper.social_posts (
    platform text not null,
    post_id text not null,
    topic_id text not null references scraper.topics(id) on delete cascade,
    text text not null,
    author_name text,
    author_url text,
    url text,
    published_at text not null,
    first_seen_at text not null,
    last_seen_at text not null,
    query text,
    mentions_product smallint not null default 0 check (mentions_product in (0, 1)),
    views bigint,
    likes bigint,
    comments bigint,
    shares bigint,
    sentiment text,
    sentiment_score double precision check (sentiment_score between -1 and 1),
    sentiment_topics text not null default '[]',
    sentiment_analyzer text,
    sentiment_status text not null default 'pending',
    sentiment_attempts integer not null default 0 check (sentiment_attempts >= 0),
    primary key (platform, post_id, topic_id)
);
create index if not exists idx_social_posts_topic
    on scraper.social_posts(topic_id, published_at desc);
create index if not exists idx_social_posts_sentiment
    on scraper.social_posts(topic_id, sentiment_status, published_at desc);

create table if not exists scraper.social_post_stats (
    platform text not null,
    post_id text not null,
    topic_id text not null,
    captured_at text not null,
    views bigint,
    likes bigint,
    comments bigint,
    shares bigint,
    primary key (platform, post_id, topic_id, captured_at)
);

create table if not exists scraper.social_refreshes (
    topic_id text not null references scraper.topics(id) on delete cascade,
    platform text not null,
    refreshed_at text not null,
    primary key (topic_id, platform)
);

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

create table if not exists scraper.api_usage (
    day text not null,
    api text not null,
    units bigint not null default 0 check (units >= 0),
    primary key (day, api)
);

alter table scraper.topics enable row level security;
alter table scraper.videos enable row level security;
alter table scraper.video_stats enable row level security;
alter table scraper.places enable row level security;
alter table scraper.place_snapshots enable row level security;
alter table scraper.comments enable row level security;
alter table scraper.summaries enable row level security;
alter table scraper.social_posts enable row level security;
alter table scraper.social_post_stats enable row level security;
alter table scraper.social_refreshes enable row level security;
alter table scraper.marketplace_products enable row level security;
alter table scraper.marketplace_refreshes enable row level security;
alter table scraper.api_usage enable row level security;
