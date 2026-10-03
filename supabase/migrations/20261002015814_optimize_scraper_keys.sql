alter table scraper.comments
    add column if not exists row_key bigint generated always as identity;

alter table scraper.comments
    add constraint comments_pkey primary key (row_key);

create index if not exists idx_places_topic_id
    on scraper.places(topic_id);
