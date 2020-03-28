
create table notes (
    name text primary key,
    content blob,
    created_utc text,   -- Seconds since epoch
    modified_utc text   -- Seconds since epoch
);

create table daily_notes (
    card_date text primary key,  -- YYYY-MM-DD
    card_name text not null,
    FOREIGN KEY(card_name) REFERENCES notes(name)
);

create table default_directory (
    absolute_path text  -- e.g. /home/<username>/timeline/zk or null for current working directory
);

