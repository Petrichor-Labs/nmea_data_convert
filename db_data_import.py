import sys

import pandas as pd
import psycopg2
import sqlalchemy  # import create_engine
import sqlalchemy.exc

from column_casting import columns_to_cast, datatype_dict
import db_creds
import db_utils

# 'fail', 'replace', or 'append', see https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_sql.html
IF_EXISTS_OPT = 'append'


# uses psycopg2.connection.cursor.execute()
def _send_data_to_db(dfs: list[pd.DataFrame], table_name_base: str, table_name_suffixes=None, dtypes=None):
    table_names = []

    # Put data in database
    for df_idx, df in enumerate(dfs):
        table_name = table_name_base
        if table_name_suffixes:
            table_name = table_name + '_' + table_name_suffixes[df_idx]

        # Create column datatypes collection

        # Create table in database for talker type in current dataframe

        # Create SQL INSERT command

        # Write current dataframe to database table for talker of this dataframe

        table_names.append(table_name)

    return table_names


# uses pandas.DataFrame.to_sql()
def send_data_to_db(dfs: list[pd.DataFrame], table_name_base: str, table_name_suffixes=None, dtypes=None):
    db_access_str = f'postgresql://{db_creds.DB_USER}:{db_creds.DB_PASSWORD}@{db_creds.DB_HOST}:{db_creds.DB_PORT}/{db_creds.DB_NAME}'
    engine = sqlalchemy.create_engine(db_access_str)

    table_names = []

    # Put data in database
    for df_idx, df in enumerate(dfs):

        if_exists_opt_loc = IF_EXISTS_OPT

        table_name = table_name_base
        if table_name_suffixes:
            table_name = table_name + '_' + table_name_suffixes[df_idx]

        try:
            df.to_sql(table_name, engine, method='multi', if_exists=if_exists_opt_loc, index=False, dtype=dtypes)
        except (sqlalchemy.exc.OperationalError, psycopg2.OperationalError) as ex:
            # Print error text bold and red
            sys.exit(f"\n\n\033[1m\033[91mERROR writing to database:\n  {ex}\033[0m\n\nExiting.\n\n")

        table_names.append(table_name)

    return table_names

# TODO: Create separate table for log file IDs and names. Check what the current larged ID is, then append a column to
# the dfs with that ID + 1, and a row to the log file table with that ID and the log file name, or something like that
