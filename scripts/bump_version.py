"""
Module that has two functions:
- run(..) method is a script, run with `zk script bump_version` to create the
  version table and set the version 1
- provide functionality to upgrade and rollback the database

The run method can be deleted when all databases have been migrated to use
schema_version table. Afterwards, merge also sql/version.sql into sql/schema.sql.
"""

import os
import sys
import sqlite3


def run(database_handle: sqlite3.Connection):
    """ Create the schema_version table. This is prerequisite to run ugprade and rollback functionality """
    project_folder = os.path.dirname(os.path.abspath(sys.argv[0]))
    sql_path = os.path.join(project_folder, 'sql', 'version.sql')
    _execute_script(database_handle, sql_path)


def _get_version(database_handle: sqlite3.Connection):
    cursor = database_handle.cursor()
    cursor.execute('select version from schema_version;')
    version = int(cursor.fetchone()[0])
    cursor.close
    return version


def _execute_script(database_handle: sqlite3.Connection, script_path: str):
    """ @Safety: It might fail """
    cursor = database_handle.cursor()
    with open(script_path, 'r') as fd:
        sql = fd.read()
        cursor.executescript(sql)
    database_handle.commit()
    cursor.close()


def _set_version(database_handle: sqlite3.Connection, version: int):
    version_row = (version,)
    cursor = database_handle.cursor()
    cursor.execute('delete from schema_version')
    cursor.execute('insert into schema_version(version) values (?)', version_row)
    database_handle.commit()
    cursor.close()


def upgrade_version_up(database_handle: sqlite3.Connection, next_version: int):
    """ Install the next schema version `sql/upgrade_{current_version}_to_{next_version}.sql`,
    but only if the next version is current version + 1.
    """
    expected_current_version = next_version - 1
    project_folder = os.path.dirname(os.path.abspath(sys.argv[0]))
    sql_name = f'upgrade_{expected_current_version}_to_{next_version}.sql'
    sql_path = os.path.join(project_folder, 'sql', sql_name)
    if not os.path.isfile(sql_path):
        raise RuntimeError(f'Missing sql path: {sql_path}')
    current_version = _get_version(database_handle)
    if current_version != expected_current_version:
        raise RuntimeError(f'Invalid version bump, going from {current_version} to {next_version}')

    _execute_script(database_handle, sql_path)
    _set_version(database_handle, next_version)


def rollback_version_down(database_handle: sqlite3.Connection, next_version: int):
    """ Install the previous schema version `sql/rollback_{current_version}_to_{next_version}.sql`,
    but only if the next version is current version - 1.
    """
    expected_current_version = next_version + 1
    project_folder = os.path.dirname(os.path.abspath(sys.argv[0]))
    sql_name = f'rollback_{expected_current_version}_to_{next_version}.sql'
    sql_path = os.path.join(project_folder, 'sql', sql_name)
    if not os.path.isfile(sql_path):
        raise RuntimeError(f'Missing sql path: {sql_path}')
    current_version = _get_version(database_handle)
    if current_version != expected_current_version:
        raise RuntimeError(f'Invalid version bump, going from {current_version} to {next_version}')

    _execute_script(database_handle, sql_path)
    _set_version(database_handle, next_version)

