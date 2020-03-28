-- Contains a single row: the version number of current database
create table schema_version (
    version int not null  -- the version number
);

-- Insert the initial version
insert into schema_version(version) values (1);

