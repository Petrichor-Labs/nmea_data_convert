IF_EXISTS_OPT = 'append'  # 'fail', 'replace', or 'append', see https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_sql.html


import os
import sys

import psycopg2
import sqlalchemy  # import create_engine

# Local modules/libary files:
import db_creds


def send_data_to_db(log_file_path, dfs, table_name_base, table_name_suffixes=None, dtypes=None):

    log_file_name = os.path.basename(log_file_path)

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
        except (sqlalchemy.exc.OperationalError, psycopg2.OperationalError) as e:
            sys.exit(f"\n\n\033[1m\033[91mERROR writing to database:\n  {e}\033[0m\n\nExiting.\n\n")  # Print error text bold and red

        table_names.append(table_name)
    
    return table_names

# TODO: Create separate table for log file IDs and names. Check what the current larged ID is, then append a column to
# the dfs with that ID + 1, and a row to the log file table with that ID and the log file name, or something like that
