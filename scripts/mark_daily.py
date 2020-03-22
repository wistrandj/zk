""" Read all open cards from legacy format i.e. the first line has YYYY-MM-DD Daily
and convert them into new format i.e. mark them as daily notes in the database.

Usage:

- Change the directory into the folder that contains all the cards
- Run the script

    $ python /usr/local/src/zk/scripts/mark_daily.py  <path to the database>

"""

import os
import re
import sys
import glob
import typing
import sqlite3
import datetime as dt


def mark_as_daily(card_name: str, date: dt.date, database_handle: sqlite3.Connection):
    args = (card_name, date.strftime('%F'))
    cursor = database_handle.cursor()
    cursor.execute('insert into daily_notes(card_name, card_date) values (?, ?)', args)
    database_handle.commit()
    cursor.close()


database_path = sys.argv[1]
is_daily_re = re.compile('^([0-9][0-9][0-9][0-9])-([0-9][0-9])-([0-9][0-9]) Daily')

if not os.path.isfile(database_path):
    raise RuntimeError('Database')

database_handle = sqlite3.connect(database_path)

all_files = glob.glob('*')


for card_name in all_files:
    card_path = card_name
    with open(card_path, 'r') as fd:
        firstline = fd.readline()
        m = is_daily_re.match(firstline)
        if m:
            yyyy, mm, dd = m.group(1), m.group(2), m.group(3)
            yyyy, mm, dd = int(yyyy), int(mm), int(dd)
            date = dt.date(year=yyyy, month=mm, day=dd)
            mark_as_daily(card_name, date, database_handle)
            print(f'Daily note {card_name} for the date {date}')

