import math
import sqlite3
import time
from datetime import datetime
from sqlite3 import Connection, Cursor

from pytube import YouTube

from data_classes import YoutubeSearchResult

HISTORY_TABLE_NAME = "YOUTUBE_BOT_HISTORY"
PLAYLIST_TABLE_NAME = "YOUTUBE_BOT_PLAYLIST"

sqlite_connection: Connection
cursor: Cursor


class DatabaseConnection:

    def __init__(self):
        self.sqlite_connection = sqlite3.connect("history.db")
        self.cursor = self.sqlite_connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.sqlite_connection.close()

    def execute_commit_query(self, query: str):
        self.cursor.execute(query)
        self.sqlite_connection.commit()


def initialize_history_table():
    create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {HISTORY_TABLE_NAME} (
            SEARCH_ID VARCHAR(255) NOT NULL, 
            ADDED_BY VARCHAR(255) NOT NULL,
            TITLE VARCHAR(255) NOT NULL,                
            UPLOADER_NAME VARCHAR(255) NOT NULL,            
            WATCH_URL VARCHAR(255) NOT NULL,
            ADDED_AT VARCHAR(255) NOT NULL
        ); """
    with DatabaseConnection() as dbcon:
        dbcon.execute_commit_query(create_table_query)


def initialize_playlist_table():
    create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {PLAYLIST_TABLE_NAME} (            
            TITLE VARCHAR(255) NOT NULL,                                        
            WATCH_URL VARCHAR(255) NOT NULL,
            ADDED_AT VARCHAR(255) NOT NULL
        ); """
    with DatabaseConnection() as dbcon:
        dbcon.execute_commit_query(create_table_query)


def insert_playlist_item_to_history_db(youtube_item: YoutubeSearchResult):
    check_existing_item_query = f'select * from {HISTORY_TABLE_NAME} WHERE WATCH_URL = \'{youtube_item.watch_url}\''
    cleaned_added_by = youtube_item.added_by.replace("'", "''")
    cleaned_title = youtube_item.title.replace("'", "''")
    cleaned_uploader_name = youtube_item.uploader_name.replace("'", "''")
    insert_query = f"INSERT INTO {HISTORY_TABLE_NAME} VALUES (" \
                   f"'{youtube_item.uuid}', " \
                   f"'{cleaned_added_by}', " \
                   f"'{cleaned_title}', " \
                   f"'{cleaned_uploader_name}', " \
                   f"'{youtube_item.watch_url}', " \
                   f"'{datetime.now()}'" \
                   f")"
    delete_query = f"DELETE FROM {HISTORY_TABLE_NAME} WHERE ADDED_AT <= date('now','-7 day')"
    update_query = f"UPDATE {HISTORY_TABLE_NAME} " \
                   f"SET ADDED_AT = '{datetime.now()}' " \
                   f"WHERE WATCH_URL = '{youtube_item.watch_url}'"

    with DatabaseConnection() as dbcon:
        dbcon.cursor.execute(check_existing_item_query)
        if dbcon.cursor.fetchall():
            dbcon.cursor.execute(update_query)
        else:
            dbcon.cursor.execute(insert_query)
        dbcon.cursor.execute(delete_query)
        dbcon.sqlite_connection.commit()


async def insert_playlist_item_to_playlist(youtube: YouTube):
    insert_query = f"INSERT INTO {PLAYLIST_TABLE_NAME} VALUES (" \
                   f"'{youtube.title}', " \
                   f"'{youtube.watch_url}', " \
                   f"'{datetime.now()}'" \
                   f")"
    with DatabaseConnection() as dbcon:
        dbcon.execute_commit_query(insert_query)


def get_un_played_playlist_urls():
    with DatabaseConnection() as dbcon:
        query = f'select * from {PLAYLIST_TABLE_NAME} ORDER BY ADDED_AT DESC'
        dbcon.cursor.execute(query)
        return [record[1] for record in dbcon.cursor.fetchall()]


async def delete_oldest_playlist_entry():
    delete_query = (f"DELETE FROM {PLAYLIST_TABLE_NAME}"
                    f"ORDER BY ADDED_AT DESC"
                    f"LIMIT 1")
    with DatabaseConnection() as dbcon:
        dbcon.execute_commit_query(delete_query)


def print_history_entries():
    with DatabaseConnection() as dbcon:
        query = f'select * from {HISTORY_TABLE_NAME}'
        dbcon.cursor.execute(query)
        for item in dbcon.cursor:
            print(item)


def get_recent_history_items(page: int) -> tuple[list[tuple], int]:
    page_size = 10
    with DatabaseConnection() as dbcon:
        query = f'select * from {HISTORY_TABLE_NAME} ORDER BY ADDED_AT DESC'
        dbcon.cursor.execute(query)
        all_entries = dbcon.cursor.fetchall()
        return all_entries[(page - 1) * page_size:page * page_size], int(math.ceil(len(all_entries) / page_size))


def get_search_result_for_search_id(search_id: str):
    with DatabaseConnection() as dbcon:
        query = f"select * from {HISTORY_TABLE_NAME} WHERE SEARCH_ID = '{search_id}'"
        dbcon.cursor.execute(query)
        found_result = next(dbcon.cursor)
        if not found_result:
            return
        return YoutubeSearchResult(
            uuid=found_result[0],
            added_by=found_result[1],
            uploader_name=found_result[3],
            title=found_result[2],
            url=None,
            watch_url=found_result[4],
        )


if __name__ == '__main__':
    initialize_history_table()
    initialize_playlist_table()
    # for i in range(20):
    #     time.sleep(1)
    #     insert_playlist_item(
    #         YoutubeSearchResult(
    #             uuid="Test",
    #             added_by="SpeedRanger",
    #             uploader_name="Claris Official Youtube Channel",
    #             title="Irony",
    #             url="https://youtube.com/123123123"
    #         )
    #     )
    # items, _ = get_recent_history_items(1)
    # for i, item in enumerate(items):
    #     print(item)
    # insert_playlist_item_to_history_db(YoutubeSearchResult(
    #     uuid="39b071bf-2e8c-4dcf-9944-86e64647a3e3",
    #     added_by="SpeedRanger",
    #     uploader_name="WaveMusic",
    #     title="Said The Sky - Show & Tell (Lyrics / Lyric Video) feat. Claire Ridgely",
    #     url="https://youtube.com/watch?v=dPfNdHNKHnk",
    #     watch_url="https://youtube.com/watch?v=dPfNdHNKHnk"
    # ))
    print_history_entries()
