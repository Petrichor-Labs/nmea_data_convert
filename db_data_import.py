import sys

import pandas as pd
import psycopg2

from column_casting import db_datatypes
from db_utils import create_table, run_db_command

# # 'fail', 'replace', or 'append', see https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.to_sql.html
# IF_EXISTS_OPT = 'append'


# uses psycopg2.connection.cursor.execute()
def send_data_to_db(dfs: list[pd.DataFrame], table_name_base: str, table_name_suffixes=None, dtypes=None):
    table_names = []

    # Put data in database
    for df_idx, df in enumerate(dfs):
        table_name = table_name_base
        if table_name_suffixes:
            table_name = table_name + '_' + table_name_suffixes[df_idx]

        # Create column datatypes collection
        columns: list[dict] = []
        for name, datatype in db_datatypes.items():
            if name in df.columns:
                columns.append({'name': name, 'datatype': datatype})

        # Create table in database for talker type in current dataframe
        try:
            create_table(table_name, columns)
        except psycopg2.OperationalError as ex:
            # Print error text bold and red
            sys.exit(f"\n\n\033[1m\033[91mERROR creating database tables:\n  {ex}\033[0m\n\nExiting.\n\n")

        # Contains all values that must be inserted into the placeholders in the SQL command
        values = []

        # Create an SQL INSERT command, but use placeholders for inputs.
        # Data gets inserted into the query by the execute() function.
        db_command = f"INSERT INTO \"{table_name}\" ("

        # Keys placeholders
        for _, col in enumerate(df.columns):
            # Add placeholder in string for key
            db_command = db_command + str(col) + ", "
        # Don't append a comma after the last key
        if db_command[-2:] == ", ":
            db_command = db_command[:-2]

        db_command = db_command + ") VALUES "

        # Value placeholders for one row
        #   (%s, %s, ..., %s)
        placeholders_row = '('
        for _ in range(df.shape[1]):
            # Add placeholder in string for row value
            placeholders_row = placeholders_row + "%s, "
        # Don't append a comma after the last value of a row
        if placeholders_row[-2:] == ", ":
            placeholders_row = placeholders_row[:-2]
        placeholders_row = placeholders_row + ')'

        # Value placeholders for all the rows
        #   (%s, %s, ..., %s), (%s, %s, ..., %s), ..., (%s, %s, ..., %s)
        for idx in range(df.shape[0]):
            # Add placeholder in string for whole row
            db_command = db_command + placeholders_row + ", "

            # Add all values of a row to values list
            values.extend(df.values[idx])
        # Don't append a comma after the last row
        if db_command[-2:] == ", ":
            db_command = db_command[:-2]

        db_command = db_command + ';'

        # Replace all types that are not compatible with psycopg2 with None
        values = [None if (type(v) == type(pd.NaT) or str(v) == "nan") else v for v in values]  # noqa: E721

        # Write current dataframe to database table for talker of this dataframe
        try:
            run_db_command(db_command, tuple(values))
        except psycopg2.OperationalError as ex:
            # Print error text bold and red
            sys.exit(f"\n\n\033[1m\033[91mERROR writing to database:\n  {ex}\033[0m\n\nExiting.\n\n")

        table_names.append(table_name)

    return table_names


# # uses pandas.DataFrame.to_sql()
# def _send_data_to_db(dfs: list[pd.DataFrame], table_name_base: str, table_name_suffixes=None, dtypes=None):
#     db_access_str = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
#     engine = sqlalchemy.create_engine(db_access_str)
#
#     table_names = []
#
#     # Put data in database
#     for df_idx, df in enumerate(dfs):
#
#         if_exists_opt_loc = IF_EXISTS_OPT
#
#         table_name = table_name_base
#         if table_name_suffixes:
#             table_name = table_name + '_' + table_name_suffixes[df_idx]
#
#         try:
#             df.to_sql(table_name, engine, method='multi', if_exists=if_exists_opt_loc, index=False, dtype=dtypes)
#         except (sqlalchemy.exc.OperationalError, psycopg2.OperationalError) as ex:
#             # Print error text bold and red
#             sys.exit(f"\n\n\033[1m\033[91mERROR writing to database:\n  {ex}\033[0m\n\nExiting.\n\n")
#
#         table_names.append(table_name)
#
#     return table_names

# TODO: Create separate table for log file IDs and names. Check what the current largest ID is, then append a column to
# the dfs with that ID + 1, and a row to the log file table with that ID and the log file name, or something like that
