import os
import sqlite3
import datetime as dt
from typing import *


def smart_date(human_input: List[str]) -> dt.date:
    date = dt.date.today()
    words = ' '.join(human_input).lower().split()

    weekdays_short = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    weekdays_long  = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    weekdays = weekdays_short + weekdays_long

    day = dt.timedelta(days=1)

    if len(words) == 0 or words[0] == 'today':
        return date
    elif words[0] == 'yesterday':
        return date - dt.timedelta(days=1)
    elif words[0] == 'tomorrow':
        return date + dt.timedelta(days=1)
    elif words[0] == 'next' and words[1] in weekdays:
        while range(7):
            date = date + dt.timedelta(days=1)
            short, long = date.strftime('%a %A').lower().split()
            if words[1] in [short, long]:
                return date
    elif words[0] == 'last':
        date = date - dt.timedelta(days=1)
        while range(7):
            date = date - dt.timedelta(days=1)
            short, long = date.strftime('%a %A').lower().split()
            if words[1] in [short, long]:
                return date

    raise ValueError('Invalid date string')


def daily_card_name(date: dt.date, database_handle: sqlite3.Connection) -> Optional[str]:
    """ Return the name of a daily card for given date, if one exists. Otherwise None.
    @Robustness: Not exception safe """
    args = (date.strftime('%F'),)
    cursor = database_handle.cursor()
    cursor.execute('select card_name from daily_notes where card_date = ?', args)
    card_name_row = cursor.fetchone()
    cursor.close()
    if card_name_row:
        return card_name_row[0]
    return None


def set_the_daily_card(card_name: str, date: dt.date, database_handle: sqlite3.Connection):
    """ Mark an existing card as daily card
    @Robustness: Not exception safe
    """
    args = (card_name, date.strftime('%F'))
    cursor = database_handle.cursor()

    cursor.execute('select 1 from daily_notes where card_date = ?', (args[1],))
    card_exists = cursor.fetchone()
    if card_exists is not None:
        raise RuntimeError(f'Daily card exists already for {args[1]}')

    cursor.execute('insert into daily_notes(card_name, card_date) values (?, ?)', args)
    database_handle.commit()
    cursor.close()
