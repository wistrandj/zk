import os
import re
import sqlite3
from typing import *

class NoteDatabase:
    IS_MAJOR_NUMBER = re.compile('^[0-9]+$')
    IS_ANY_NOTE = re.compile('^[0-9]+|[0-9]+[a-z]|[0-9]+([a-z][0-9]+)+')

    def __init__(self, sqlite_connection: sqlite3.Connection):
        """ Start using fully initialized database """
        self._database_handle = sqlite_connection

    def commit(self):
        self._database_handle.commit()

    def find_major_notes(self) -> Set[str]:
        cursor = self._database_handle.cursor()
        cursor.execute('select name from notes')
        notes_in_database = cursor.fetchall()
        cursor.close()

        major_notes = set()
        for note in notes_in_database:
            note = note[0]
            if NoteDatabase.IS_MAJOR_NUMBER.match(note):
                major_notes.add(note)
        return major_notes

    def find_all_notes(self) -> Set[str]:
        cursor = self._database_handle.cursor()
        cursor.execute('select name from notes')
        notes_in_database = cursor.fetchall()
        cursor.close()

        major_notes = set()
        for note in notes_in_database:
            note = note[0]
            if NoteDatabase.IS_ANY_NOTE.match(note):
                major_notes.add(note)
        return major_notes


    def save_card(self, card_name: str, card_path: str):
        if not os.path.isfile(card_path):
            raise EnvironmentError(f'Missing card: {card_path}')

        cursor = self._database_handle.cursor()
        stat = os.stat(card_path)
        created_utc  = int(stat.st_ctime)
        modified_utc = int(stat.st_mtime)
        with open(card_path, 'rb') as fd:
            content = fd.read()
            sql1 = ('insert into notes(name, content, created_utc, modified_utc) values (?, ?, ?, ?)')
            sql2 = ('on conflict(name) do update set content=excluded.content, modified_utc=excluded.modified_utc')
            args = (card_name, content, created_utc, modified_utc)

            cursor.execute(' '.join((sql1, sql2)), args)

        self.commit()

    def card_modified_utc_time_in_seconds(self, card_name: str) -> Optional[int]:
        cursor = self._database_handle.cursor()
        cursor.execute('select modified_utc from notes where name = ?', (card_name,))
        modified_time = cursor.fetchone()
        cursor.close()

        if not modified_time:
            return None
        return int(modified_time[0])
