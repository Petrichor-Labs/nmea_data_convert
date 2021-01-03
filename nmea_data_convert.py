import pynmea2
import argparse
import sys
import os
from datetime import datetime
import pandas as pd
from collections import namedtuple
import re
import numpy as np
import functools
print = functools.partial(print, flush=True)  # Prevent print statements from buffering till end of execution

# Local modules/libary files:
import db_data_import
import db_creds
import db_utils
import db_table_lists


def parse_and_validate_args():

    parser = argparse.ArgumentParser()
    parser.add_argument("filepath",
                            help="file system path to file containing NMEA data")
    parser.add_argument("output_method",
                            choices=['csv', 'db', 'both'],
                            help="where to output data: CSV files, database, or both")
    parser.add_argument("--drop_previous_db_tables", "--dropt",
                            action="store_true",
                            help="drop previous DB tables before importing new data; only applies when output_method is 'db' or 'both'")
    parser.add_argument("--backfill_datetimes", "--bfdt",
                            action="store_true",
                            help="backfill datetimes where missing by extrapolating from messages with datetime information")

    args = parser.parse_args()

    if os.path.isfile(args.filepath):
        return args
    else:
        sys.exit(f"\nFile {args.filepath} does not exist.\n\nExiting.\n")


def open_file(filepath):

  return open(filepath, encoding='utf-8')


def read_file(file):

    sentences = []

    for line_idx, line in enumerate(file.readlines()):
        try:
            sentence = pynmea2.parse(line)
            sentences.append(sentence)
        except pynmea2.ParseError as e:
            print(f'Parse error on line {line_idx+1}: {e}')
            continue

    return sentences


def categorize_sentences(sentences):

    # Make a list of all sentence types
    sentence_types = []
    for dts_sentence in sentences:
        if get_sentence_type(dts_sentence.sentence) not in sentence_types:
            sentence_types.append(get_sentence_type(dts_sentence.sentence))

    # Create a list of sentence sets (a separate list for each sentence type)
    sentence_sets = [[] for _ in range(len(sentence_types))]
    for dts_sentence in sentences:
        type_idx = sentence_types.index(get_sentence_type(dts_sentence.sentence))
        sentence_sets[type_idx].append(dts_sentence)  # Add each sentence to the appropriate list

    return sentence_sets


# Look for the beginning of cycles, get the timestamp for each cycle,
#   pair that timestamp with each sentence from the cycle
# This function assumes that the sentence that starts the cycle contains a date and time stamp
#   which may only be true for RMC sentences
def datetime_stamp_sentences(sentences, cycle_start='GNRMC'):

    datetime_stamped_sentences = []

    date_time = None

    for sentence in sentences:

        # TODO: Search through cycle to find sentence(s) containing date and/or time

        # If sentence is the first in a cycle, get the timestamp 
        if sentence.talker + sentence.sentence_type == cycle_start:
            
            if hasattr(sentence, 'timestamp'):
                time = sentence.timestamp
            else:
                time = None
            
            if hasattr(sentence, 'datestamp'):
                date = sentence.datestamp
            else:
                date = None
            
            if date and time:  # Sentence contains both date and time
                date_time = datetime.combine(date, time)

        datetime_stamped_sentence = DateTimeStampedSentence(sentence, date_time)
        datetime_stamped_sentences.append(datetime_stamped_sentence)

    return datetime_stamped_sentences


# To properly assign cycle IDs, the cycle_start talker+sentence_type must appear once and only once in each cycle
def assign_cycle_ids(dts_sentences, cycle_start='GNRMC'):
    # TODO: Check database for highest cycle_id and start there so that IDs will be unique across runs of this script

    cycle_id = -1

    for sen_idx, dts_sentence in enumerate(dts_sentences):
        if dts_sentence.sentence.talker + dts_sentence.sentence.sentence_type == cycle_start:
            cycle_id += 1
        dts_sentences[sen_idx].cycle_id = cycle_id

    return dts_sentences


# Get list of groups (lists) of sentences that should be merged together
# Sentences to be merged are those that have the same type and that are (assumed to be) 
#   part of the same cycle (e.g., msg_num 1 or 2 out of num_messages 2) and where the date and time match
# Assumes sentences that should be merged are listed together but in no particular order
# Currently only supporting merging GSV sentences
# This could probably be done easier using the cycle_id attribute, but the current implementation may be more reliable
def get_merge_groups(sentence_sets):

    merge_group_lists = [[[]] for idx in range(len(sentence_sets))]

    for set_idx, sentence_set in enumerate(sentence_sets):
        for sentence_idx, dts_sentence in enumerate(sentence_set):

            if hasattr(dts_sentence.sentence, 'num_messages') and (int(dts_sentence.sentence.num_messages) > 1) \
                and (dts_sentence.sentence.sentence_type == 'GSV'):  # If sentence needs to be merged with another sentence

                # Check whether current sentence should be merged with current group or if new group should be started
                for sentence_in_group_idx, _ in enumerate(merge_group_lists[set_idx][-1]):

                    if dts_sentence.sentence.num_messages != sentence_sets[set_idx][merge_group_lists[set_idx][-1][sentence_in_group_idx]].sentence.num_messages \
                        or dts_sentence.sentence.msg_num  == sentence_sets[set_idx][merge_group_lists[set_idx][-1][sentence_in_group_idx]].sentence.msg_num      \
                        or dts_sentence.date_time         is not sentence_sets[set_idx][merge_group_lists[set_idx][-1][sentence_in_group_idx]].date_time:

                        merge_group_lists[set_idx].append([])  # Start new merge group
                        break  # Break is necessary here so that we don't append more than one []

                merge_group_lists[set_idx][-1].append(sentence_idx)

    return merge_group_lists


def merge_groups(sentence_sets, merge_group_lists):

    for set_idx, set_merge_group_list in enumerate(merge_group_lists):
        if any(set_merge_group_list):  # If there are merge groups

            sentences_merged = []

            for merge_group in set_merge_group_list:

                if len(merge_group) > 1:  # There will be some empty sets
                    merge_group_sentences = [sentence_sets[set_idx][sen_idx] for sen_idx in merge_group]
                    merged_sentence = MergedSentence_GSV(merge_group_sentences)
                    sentence_sets[set_idx].append(merged_sentence)

                    sentences_merged = sentences_merged + merge_group_sentences

            # Remove originals to prevent duplicates, have to do it after all have been processed to prevent indexing issues
            for dts_sentence in sentences_merged:
                sentence_sets[set_idx].remove(dts_sentence)

    return sentence_sets


# Extrapolate missing datetimes
# Look at the first two consecutive cycles with datetimes, take the interval between them, and backfill datetimes
#   to cycles without datetimes based on that interval, assuming no data interruptions
# The interval from the first talker+sentence_type dataframe will be used for all dataframes
def backfill_datetimes(sentence_dfs, verbose=False):

    # Make sure sentences are in order by cycle, they may have gotten out of order when merged
    sentence_dfs = sort_dfs(sentence_dfs, sort_by='cycle_id')

    # Find time delta (interval) between sentence cyles
    interval = None
    for df in sentence_dfs:
        if not interval:
            for sen_idx, _ in enumerate(df['datetime']):

                if df['datetime'][sen_idx] and sen_idx+1 < len(df['datetime'])-1 and \
                    df['datetime'][sen_idx+1] and df['cycle_id'][sen_idx] < df['cycle_id'][sen_idx+1]:  # If this dts sentence and the next have valid datetimes
                    first_datetime  = df['datetime'][sen_idx]
                    second_datetime = df['datetime'][sen_idx+1]
                    interval = second_datetime - first_datetime
                    
                    if interval.total_seconds() > 0:  # Don't look at sentences of same type in same cycle (interval will be 0)
                        break
                    else:
                        interval = None

    if not interval:
        if verbose:
            print("Time delta between sentence cycles could not be determined, so datetimes will not be backfilled.")
        return

    pd.options.mode.chained_assignment = None  # Suppress chained_assignment warnings, default='warn'
        # See https://pandas.pydata.org/pandas-docs/stable/user_guide/indexing.html#returning-a-view-versus-a-copy
        # TODO: Investigate how to do this better and remove this warning suppression

    for df_idx, df in enumerate(sentence_dfs):

        # Find sentences without datetime value
        datetime_bools   = df['datetime'].isnull()
        no_datetime_idxs = datetime_bools[datetime_bools].index.tolist()

        # Find first sentence in this dataframe with datetime
        first_datetime_idx = (~datetime_bools).idxmax()

        # Get lists of indices to process
        no_datetime_idxs_preceding  = [idx for idx in no_datetime_idxs if idx < first_datetime_idx]
        no_datetime_idxs_succeeding = [idx for idx in no_datetime_idxs if idx > first_datetime_idx]

        # From first sentence with datetime, fill in preceding sentences moving backwards
        no_datetime_idxs_preceding.reverse()
        for sen_idx in no_datetime_idxs_preceding:

            # If sentence is of same talker+sentence_type and different cycle
            if df['cycle_id'][sen_idx] < df['cycle_id'][sen_idx+1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx+1] - interval
            # If sentence is of same talker+sentence_type and same cycle
            if df['cycle_id'][sen_idx] == df['cycle_id'][sen_idx+1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx+1]

            df['datetime_is_interpolated'][sen_idx] = True

        # Fill in succeeding sentences' datetimes
        for sen_idx in no_datetime_idxs_succeeding:

            # If sentence is of same talker+sentence_type and different cycle
            if df['cycle_id'][sen_idx] > df['cycle_id'][sen_idx-1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx-1] + interval
            # If sentence is of same talker+sentence_type and same cycle
            if df['cycle_id'][sen_idx] == df['cycle_id'][sen_idx-1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx-1]

            df['datetime_is_interpolated'][sen_idx] = True


def sentences_to_dataframes(sentence_sets):

    dfs = []

    for set_idx, sentence_set in enumerate(sentence_sets):
        if sentence_sets[set_idx][0].sentence.sentence_type == 'GSV':
            fields = expand_GSV_fields(sentence_sets[set_idx][0].sentence.fields)
        else:
            fields = sentence_sets[set_idx][0].sentence.fields
        columns = [column_tuple[1] for column_tuple in fields]

        # Add columns for data fields missing from class
        # TODO: Fork pynmea2 module to correct
        # Issure reported here: https://github.com/Knio/pynmea2/issues/118
        if sentence_sets[set_idx][0].sentence.sentence_type == 'RMC':
            columns.append('mode')

        columns.insert(0, 'cycle_id')
        columns.insert(1, 'datetime')
        columns.insert(2, 'datetime_is_interpolated')
        columns.insert(3, 'talker')
        columns.insert(4, 'sentence_type')

        df = pd.DataFrame(columns=columns)

        for dts_sentence in sentence_set:

            row_data = dts_sentence.sentence.data.copy()

            date_time = dts_sentence.date_time
            row_data.insert(0, dts_sentence.cycle_id)
            row_data.insert(1, date_time)
            row_data.insert(2, dts_sentence.datetime_is_interpolated)
            row_data.insert(3, dts_sentence.sentence.talker)
            row_data.insert(4, dts_sentence.sentence.sentence_type)

            # Single GSV sentences have data for 4 SVs and merged GSV sentences have data for 12 SVs, so fill single GSV sentences with NaNs for SV 5-12 data
            # TODO: Is this necessary? Use None instead of ''?
            if dts_sentence.sentence.sentence_type == 'GSV':
                placeholders = ['']  * (len(columns) - len(row_data))
                row_data = row_data + placeholders

            df.loc[len(df)] = row_data  # Append data as new row in dataframe

        dfs.append(df)

    pd.set_option('display.max_rows', None)
    # pd.set_option('display.max_columns', None)
    # pd.set_option('display.width', 180)

    # Corrrect data types of columns
    dfs = [correct_data_types(df) for df in dfs]

    return dfs


def sort_dfs(dfs, sort_by='cycle_id', ascending=True):

    for df_idx, _ in enumerate(dfs):
        dfs[df_idx] = dfs[df_idx].sort_values(sort_by, ascending=ascending)
        dfs[df_idx] = dfs[df_idx].reset_index(drop=True)

    return dfs


def correct_data_types(df):

    df.replace(to_replace=pd.NaT, value='', inplace=True)  # Do this replace first because pd.Nat won't be replaced with np.NaN
    df.replace(to_replace='',     value=np.NaN, inplace=True)

    columns_not_to_cast = ['cycle_id', 'sentence_type', 'talker', 'datetime']
    columns_to_cast = [column_name for column_name in df.columns if column_name not in columns_not_to_cast]

    if df['sentence_type'][0] == 'GSV':

        for column in columns_to_cast:
            df[column] = df[column].astype('float').astype('Int16')  # Smallest Int type in Postgres is 2 bytes with a max value of +32,767
                # Cast as float first to get around bug: https://stackoverflow.com/questions/60024262/error-converting-object-string-to-int32-typeerror-object-cannot-be-converted

    df['datetime'].replace(to_replace=np.NaN, value=pd.NaT, inplace=True)  # Needed for backfill_datetimes() to work properly

    return df


def dfs_to_csv(sentence_dfs, input_file_path, verbose=False):

    input_file_name = os.path.basename(input_file_path)
    input_file_name = os.path.splitext(input_file_name)[0]

    for df_idx, df in enumerate(sentence_dfs):
        filename = f"{input_file_name}_{df['talker'][0]}{df['sentence_type'][0]}.csv"
        df.to_csv(filename, index=False)  # Save to cwd

        if verbose:
            if df_idx is 0:  # If this is the first df
                print(f"data from logfile '{input_file_path}' written to:")
            print("  " + filename)


def dfs_to_db(sentence_dfs, input_file_path, verbose=False):

    table_name_base = 'nmea'
    # Pass lowercase 'talker_sentencetype' as table name suffixes
    table_name_suffixes = [f"{df['talker'][0]}_{df['sentence_type'][0]}".lower() for df in sentence_dfs]

    table_names = db_data_import.send_data_to_db(input_file_path, sentence_dfs, table_name_base, table_name_suffixes)

    if verbose:
        print(f"data from logfile '{input_file_path}' written to:")
        for table_name in table_names:
            print(f"  '{table_name}' table in '{db_creds.DB_NAME}' database")


def get_sentence_type(sentence):

    return sentence.talker + sentence.sentence_type


class DateTimeStampedSentence:

    def __init__(self, sentence, date_time):

        # TODO: Check if inputs are of correct types (use isinstance())
        # https://stackoverflow.com/questions/14570802/python-check-if-object-is-instance-of-any-class-from-a-certain-module

        self.cycle_id = None
        self.sentence = sentence  # 'sentence' is instance of class from pynmea2
        self.date_time = date_time
        self.datetime_is_interpolated = False

    def __str__(self):

        return str(self.cycle_id) + ' ' + str(self.sentence) + ' ' + str(self.date_time)


class MergedSentence_GSV:
    #TODO: Have MergedSentence_GSV inherit from DateTimeStampedSentence ?
    
    def __init__(self, merge_group):
        
        self.cycle_id = merge_group[0].cycle_id
        self.date_time = merge_group[0].date_time
        self.datetime_is_interpolated = False

        Sentence = namedtuple('sentence', 'talker sentence_type fields data')
        
        talker        = merge_group[0].sentence.talker
        sentence_type = merge_group[0].sentence.sentence_type

        # Add fields for SVs 5-12. 12 SVs seems to be a common number of maximum supported SVs for GNSS devices
        fields = expand_GSV_fields(merge_group[0].sentence.fields)        

        # Merge SV data from sentences after the first with the data from the first sentences
        data = merge_group[0].sentence.data
        data[1] = np.NaN  # msg_num doesn't apply to merged sentence
        for dts_sentence in merge_group[1:]:
            data = data + dts_sentence.sentence.data[3:]

        self.sentence = Sentence(talker, sentence_type, fields, data)

    def __str__(self):

        return str(self.cycle_id) + ' ' + str(self.sentence.talker) + ' ' + str(self.sentence.sentence_type) + ' ' + str(self.sentence.data) + ' ' + str(self.date_time)


# Add fields for SVs 5-12. 12 SVs seems to be a common number of maximum supported SVs for GNSS devices
def expand_GSV_fields(fields):

    fields = list(fields)  # Make mutable
    fields_to_duplicate = [field for field in fields if field[0].endswith('4')]  # Original GSV sentence supports 0-4 SVs, so copy and change fields for SV 4
    for SV_idx in range(5, 12+1):
        new_fields = [(re.sub(r'4$', str(SV_idx), field[0]), re.sub(r'4$', str(SV_idx), field[1])) for field in fields_to_duplicate]
        fields = fields + new_fields
    fields = tuple(fields)  # Return to original immutable tuple state

    return fields


# Do data processing that we will always want to do
def process_data_common(sentences, cycle_start='GNRMC'):
    
    dts_sentences = datetime_stamp_sentences(sentences, cycle_start)
        # 'dts' -> 'datetime stamped'
    dts_sentences = assign_cycle_ids(dts_sentences, cycle_start='GNRMC')
    sentence_sets = categorize_sentences(dts_sentences)
    merge_group_lists = get_merge_groups(sentence_sets)
    sentence_sets = merge_groups(sentence_sets, merge_group_lists)
    sentence_dfs  = sentences_to_dataframes(sentence_sets)

    return sentence_dfs


def main():

    args = parse_and_validate_args()

    print("\nReading in data... ", end="")
    file = open_file(args.filepath)
    sentences = read_file(file)
    print("done.")
    
    print("\nProcessing data... ", end="")
    sentence_dfs = process_data_common(sentences, cycle_start='GNRMC')  # Cycle starts with 'RMC' sentence
    if args.backfill_datetimes:
        dts_sentences = backfill_datetimes(sentence_dfs, verbose=True)
    print("done.")
    
    if (args.output_method == 'csv' or args.output_method == 'both'):
        print("\nWriting data to CSVs... ", end="")
        dfs_to_csv(sentence_dfs, args.filepath, verbose=True)
        print("done.")

    if (args.output_method == 'db'  or args.output_method == 'both'):
        
        if args.drop_previous_db_tables:
            print()
            db_utils.drop_db_tables(db_table_lists.nmea_tables, verbose=True)

        print("\nWriting data to database... ", end="")
        dfs_to_db(sentence_dfs, args.filepath, verbose=True)
        print("done.")

    print("\nAll done. Exiting.\n\n")

if __name__ == '__main__':

    main()
