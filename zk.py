import os
import re
import sys
import glob
import time
import socket
import logging
import sqlite3
import getpass
import argparse
import datetime as dt
from typing import *

import new_note
import note_folder as NF
from note_folder import NoteFiles
from note_folder import NotesDirectory
from note_database import NoteDatabase
import daily

log = logging.getLogger(__name__)


class Notes:
    def __init__(self, directory_path: str, database_path: str):
        self._sqlite_connection = sqlite3.connect(database_path)
        self._directory = NotesDirectory(directory_path)
        self._card_files = NoteFiles(self._directory)
        self._card_storage = NoteDatabase(self._sqlite_connection)

    @property
    def open_notes(self):
        return self._card_files

    @property
    def persistent_notes(self):
        return self._card_storage

    @property
    def database_handle(self):
        return self._sqlite_connection


def check_database(database_path: str) -> bool:
    """ Check if there's an notes database in the path of giben argument
    @Robustness: Doesn't check if the database is readable and all tables
    """
    return os.path.isfile(database_path)


def check_open_notes_directory(database_handle: sqlite3.Connection) -> str:
    """ Return the directory to open notes. It can be either saved in the database, or current working directory.
    @Robustness: Not exception safe and doesn't check if the directory is writable
    """
    cursor = database_handle.cursor()
    cursor.execute('select absolute_path from default_directory;')
    notes_folder_row = cursor.fetchone()
    cursor.close()

    if notes_folder_row and os.path.isdir(notes_folder_row[0]):
        note_folder = notes_folder_row[0]
        if not os.path.isdir(note_folder):
            raise EnvironmentError(f'The notes folder {note_folder} does not exists!')
        return note_folder

    return os.getcwd()


def save_open_notes_into_database(app: Notes):
    for card_name in app.open_notes.find_all_notes():
        card_path = app.open_notes.fullpath_of_open_card(card_name)
        app.persistent_notes.save_card(card_name, card_path)


def remove_default_location(app: Notes):
    with app.database_handle as db:
        cursor = db.cursor()
        cursor.execute('delete from default_directory')
        db.commit()


def set_default_location(app: Notes, note_folder: str):
    if not os.path.isdir(note_folder):
        raise EnvironmentError('The folder is missing')

    with app.database_handle:
        args = (os.path.abspath(note_folder),)
        cursor = app.database_handle.cursor()
        cursor.execute('delete from default_directory')
        cursor.execute('insert into default_directory(absolute_path) values (?)', args)


def pack_open_notes_into_database(app: Notes):
    """ Save files into database and remove all files """
    save_open_notes_into_database(app)
    notes = app.open_notes.find_all_notes()
    for card_name in notes:
        card_path = app.open_notes.fullpath_of_open_card(card_name)
        os.unlink(card_path)


def unpack_open_notes_from_database(app: Notes):
    cursor = app.database_handle.cursor()
    cursor.execute('select name, content, created_utc, modified_utc from notes;')
    for row in cursor.fetchall():
        card_name, content, created_utc, modified_utc = row
        card_name, content, created_utc, modified_utc = str(card_name), bytes(content), int(created_utc), int(modified_utc)

        app.open_notes.create_card_with_modified_time(card_name=card_name, content=content, modified_utc=modified_utc)


def hostname():
    return socket.gethostname()


def open_editor(card_path: str):
    os.system("vim -c 'normal! jj' " + card_path)


if __name__ == '__main__':
    assert sys.argv[1] == '--database'
    database_path = sys.argv[2]
    assert str(database_path)
    subcommand = sys.argv[3]
    args = sys.argv[4:]

    # @Note: Database initialization, execute with subcommands 'init' or 'init-sql <number>'
    sql_script = None
    if subcommand == 'init':
        developing_directory = os.path.dirname(sys.argv[0])
        sql_directory = os.path.join(developing_directory, 'sql')
        sql_script = os.path.join(sql_directory, 'schema.sql')
    elif subcommand == 'init-sql':
        # Temporary command for developing. Later: merge sql files into single file
        developing_directory = os.path.dirname(sys.argv[0])
        sql_directory = os.path.join(developing_directory, 'sql')
        sql_number = int(args[0])
        if sql_number > 0:
            sql_script = os.path.join(sql_directory, f'schema.{sql_number}.sql')
    if sql_script:
        if not os.path.isfile(sql_script):
            raise EnvironmentError('Invalid developing sql script!')
        with sqlite3.connect(database_path) as database_handle:
            with open(sql_script, 'r') as schema:
                cursor = database_handle.cursor()
                schema_sql = schema.read()
                cursor.executescript(schema_sql)
        sys.exit(0)  # The only command was to initialize the database

    if database_path and not check_database(database_path):
        raise EnvironmentError('the database is missing')

    if not database_path:
        # Use In-memory database if the user didn't want to use anything else.
        # This allows to use zk for open notes without a database.
        database_path = ':memory:'
        raise RuntimeError('Not supported yet')

    with sqlite3.connect(database_path) as connection_handle:
        note_folder = check_open_notes_directory(connection_handle)

    app = notes = Notes(directory_path=note_folder, database_path=database_path)
    open_notes = app.open_notes
    persistent_notes = app.persistent_notes


    # if len(open_notes.find_major_notes()) == 0:
    #    raise EnvironmentError('This folder does not seem to be for notes. Initialize it first')

    # Actions
    if subcommand == 'card':
        content = dt.datetime.now().strftime('%F\n\n\n')
        card_name = new_note.next_available_major_note(notes.open_notes, notes.persistent_notes)
        card_path = notes.open_notes.create_new_card(card_name, content)
        open_editor(card_path)
    elif subcommand == 'branch':
        card_name = new_note.next_available_subcard_name(args[0], notes.open_notes, notes.persistent_notes)
        if card_name:
            content = ''
            card_path = notes.open_notes.create_new_card(card_name, content)
            open_editor(card_path)
        else:
            raise RuntimeError("Too many notes for this major card. The sub-card 'z' already exists.")
    elif subcommand == 'daily':
        # Saves the card immediately into the database
        date = daily.smart_date(args)
        card_name = daily.daily_card_name(date, notes.database_handle)
        if not card_name:
            content = date.strftime('%F Daily\n\n\n')
            card_name = new_note.next_available_major_note(notes.open_notes, notes.persistent_notes)
            card_path = notes.open_notes.create_new_card(card_name, content)
            notes.persistent_notes.save(card_name, card_path)
            daily.set_the_daily_card(card_name, date, notes.database_handle)
        else:
            card_path = notes.open_notes.fullpath_of_open_card(card_name)
        open_editor(card_path)
    elif subcommand == 'save':
        save_open_notes_into_database(app=notes)
    elif subcommand == 'pack':
        pack_open_notes_into_database(app=notes)
    elif subcommand == 'unpack':
        unpack_open_notes_from_database(app=notes)
    elif subcommand == 'show' and len(args) > 0:
        show_cards = set()
        if args[0] == 'modified':
            cards = NF.modified_cards(notes.open_notes, notes.database_handle)
            print('Modified cards: ' + str(sorted(cards)))
        elif args[0] == 'new':
            cards = NF.new_cards(notes.open_notes, notes.database_handle)
            print('New cards: ' + str(sorted(cards)))
    elif subcommand == '--set-default-directory':
        set_default_location(notes, args[0])
    elif subcommand == '--remove-default-directory':
        remove_default_location(notes)
    else:
        log.info('No command given')
        print('No command given')

