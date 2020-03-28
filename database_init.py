"""
Module to initialize a new database file.

The difference to scripts/bump_version.py is that this module is a permanent one. The bump_version
module is used only for developing the database and the functionality from there will be migrated
to sql/schema.py when all database in use have been upgraded to newest version.
"""

import os
import sys
import sqlite3

def initialize_database(database_handle: sqlite3.Connection):
    """ Initialize an empty database. """
    project_folder = os.path.dirname(os.path.abspath(sys.argv[0]))
    schema_path = os.path.join(project_folder, 'sql', 'schema.sql')
    cursor = database_handle.cursor()
    with open(schema_path, 'r') as fd:
        cursor.executescript(fd.read())
    database_handle.commit()
    cursor.close()

