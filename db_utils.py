# TODO: Overriding the print function isn't a good way to handle this, replace with a custom library that does this
import functools
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sqlalchemy.exc

# Local modules/libary files:
import db_creds

# Prevent print statements from buffering till end of execution
print = functools.partial(print, flush=True)


def drop_db_tables(tables_to_drop: list[str], verbose=False):
    [psql_con, psql_cursor] = setup_db_connection()

    # Drop tables
    table_list = ""
    for idx, table_name in enumerate(tables_to_drop):
        table_list = table_list + table_name
        # Don't append a comma after last table name
        if idx < len(tables_to_drop) - 1:
            table_list = table_list + ", "
        if verbose:
            print(f"Dropping database table {table_name} (and any dependent objects) if it exists.")

        # Quotes arouund table names are required for case sensitivity
        drop_table_stmt = f"DROP TABLE IF EXISTS \"{table_name}\" CASCADE;"
        psql_cursor.execute(drop_table_stmt)

    free_db_connection(psql_con, psql_cursor)


def create_table(table_name: str, columns=None):
    db_command = f"CREATE TABLE IF NOT EXISTS \"{table_name}\" ("

    if columns:
        for idx, column in enumerate(columns):
            db_command = db_command + '"' + column['name'] + '" ' + column['datatype']
            # Don't append a comma after the last column declaration
            if idx < len(columns) - 1:
                db_command = db_command + ", "

    db_command = db_command + ");"

    run_db_command(db_command)


def run_db_command(db_command: str):
    [psql_con, psql_cursor] = setup_db_connection()

    # Run command on database    
    psql_cursor.execute(db_command)

    # print(psql_con.notices)
    # print(psql_con.notifies)

    free_db_connection(psql_con, psql_cursor)


def setup_db_connection():
    db_access_str = f"postgresql://{db_creds.DB_USER}:{db_creds.DB_PASSWORD}@{db_creds.DB_HOST}:{db_creds.DB_PORT}/{db_creds.DB_NAME}"

    # Start a PostgreSQL database session
    try:
        psql_con = psycopg2.connect(db_access_str)
    except (sqlalchemy.exc.OperationalError, psycopg2.OperationalError) as ex:
        # Print error text bold and red
        sys.exit(f"\n\033[1m\033[91mERROR connecting to database:\n  {ex}\033[0m\n\nExiting.\n\n")

    psql_con.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    # Open a database cursor
    psql_cursor = psql_con.cursor()

    return [psql_con, psql_cursor]


def free_db_connection(psql_con, psql_cursor):
    # Free the resources
    psql_cursor.close()
    psql_con.close()
