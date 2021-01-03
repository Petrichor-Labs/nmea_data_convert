import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import sqlalchemy
import functools
print = functools.partial(print, flush=True)  # Prevent print statements from buffering till end of execution

# Local modules/libary files:
import db_creds
import db_table_lists


def drop_db_tables(tables_to_drop, verbose=False):
    
    [psqlCon, psqlCursor] = setup_db_connection()
  
    # Drop tables
    tableList = ""
    for idx, tableName in enumerate(tables_to_drop):
        tableList = tableList + tableName
        if idx < len(tables_to_drop)-1:  # Don't append comma after last table name
            tableList = tableList + ", " 
        if verbose:
            print(f"Dropping database table {tableName} (and any dependent objects) if it exists.")

        dropTableStmt = f"DROP TABLE IF EXISTS \"{tableName}\" CASCADE;"  # Quotes arouund table names are required for case sensitivity
        psqlCursor.execute(dropTableStmt);

    free_db_connection(psqlCon, psqlCursor)


def create_table(table_name, columns=None):
    
    db_command = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
    """

    if columns:
        for idx, column in enumerate(columns):
            db_command = db_command + '"' + column['name'] + '" ' + column['datatype']
            if idx < len(columns)-1:  # Don't append a comman after the last column declaration
                db_command = db_command + ','

    db_command = db_command + ')'

    run_db_command(db_command)


def run_db_command(db_command):

    [psqlCon, psqlCursor] = setup_db_connection()

    # Run command on database    
    psqlCursor.execute(db_command);

    # print(psqlCon.notices)
    # print(psqlCon.notifies)

    free_db_connection(psqlCon, psqlCursor)


def setup_db_connection():

    db_access_str = f'postgresql://{db_creds.DB_USER}:{db_creds.DB_PASSWORD}@{db_creds.DB_HOST}:{db_creds.DB_PORT}/{db_creds.DB_NAME}'

    # Start a PostgreSQL database session
    try:
        psqlCon = psycopg2.connect(db_access_str);
    except (sqlalchemy.exc.OperationalError, psycopg2.OperationalError) as e:
        sys.exit(f"\n\033[1m\033[91mERROR connecting to database:\n  {e}\033[0m\n\nExiting.\n\n")  # Print error text bold and red
    
    psqlCon.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT);

    # Open a database cursor
    psqlCursor = psqlCon.cursor();

    return [psqlCon, psqlCursor]


def free_db_connection(psqlCon, psqlCursor):

    # Free the resources
    psqlCursor.close();
    psqlCon.close();