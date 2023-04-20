#!/usr/bin/env python

import argparse
from datetime import datetime
# TODO: Overriding the print function isn't a good way to handle this, replace with a custom library that does this
import functools
import os
import re
import sys
from typing import NamedTuple

import numpy as np
import pandas as pd
import pynmea2

from column_casting import columns_to_cast, datatype_dict, db_datatypes
import db_creds
import db_data_import
import db_table_lists
import db_utils

# Prevent print statements from buffering till end of execution
print = functools.partial(print, flush=True)


class Sentence(NamedTuple):
    talker: str
    sentence_type: str
    fields: tuple[tuple[str, str]]
    data: list


class DateTimeStampedSentence:
    def __init__(self, sentence, date_time):
        # TODO: Check if inputs are of correct types (use isinstance())
        # https://stackoverflow.com/questions/14570802/python-check-if-object-is-instance-of-any-class-from-a-certain-module

        self.cycle_id: int
        self.sentence = sentence  # 'sentence' is an instance of class from pynmea2, contains various attributes
        self.date_time = date_time
        self.datetime_is_interpolated = False
        self.sentence_is_merged_from_multiple = False

    def __str__(self):
        return str(self.cycle_id) + ' ' + str(self.sentence) + ' ' + str(self.date_time)


class MergedSentence_GSV(DateTimeStampedSentence):
    def __init__(self, merge_group: list[DateTimeStampedSentence]):
        talker = merge_group[0].sentence.talker
        sentence_type = merge_group[0].sentence.sentence_type

        # Add fields for SVs 5-12. 12 SVs seems to be a common number of maximum supported SVs for GNSS devices
        fields = expand_GSV_fields(merge_group[0].sentence.fields)

        # Merge SV data from sentences after the first with the data from the first sentences
        data = merge_group[0].sentence.data
        data[1] = np.NaN  # msg_num doesn't apply to merged sentence
        for dts_sentence in merge_group[1:]:
            data = data + dts_sentence.sentence.data[3:]

        sentence = Sentence(talker, sentence_type, fields, data)

        # call __init__ of base class
        super().__init__(sentence, merge_group[0].date_time)

        self.cycle_id = merge_group[0].cycle_id
        self.datetime_is_interpolated = False
        self.sentence_is_merged_from_multiple = True

    def __str__(self):
        return str(self.cycle_id) + ' ' + str(self.sentence.talker) + ' ' + str(self.sentence.sentence_type) + ' ' + str(self.sentence.data) + ' ' + str(self.date_time)


class MergedSentence_GSA(DateTimeStampedSentence):
    # Separate GSA sentences in the same cycle represent reporting for different constellations
    # SV with IDs 1-32 are GPS, 65-96 are GLONASS.
    # See https://www.u-blox.com/sites/default/files/products/documents/u-blox8-M8_ReceiverDescrProtSpec_%28UBX-13003221%29.pdf, Appendix A

    # TODO: Support more than two GSA sentences per cycle, if necessary

    def __init__(self, merge_group: list[DateTimeStampedSentence]):
        if len(merge_group) != 2:
            raise Exception("Merging of two and only two GSA sentences per cycle is currently supported.")

        talker = merge_group[0].sentence.talker
        sentence_type = merge_group[0].sentence.sentence_type

        # Create additional sv_id01...sv_id12 fields for other constellations, and label prefix with 'gp' for GPS, 'gl' for GLONASS and 'ga' for Galileo
        # Other data is the same between sentences (as observed in limited data)
        fields = expand_GSA_fields(merge_group[0].sentence.fields)

        # Constellation reporting may not always be in the same order, e.g. GPS may be reported before GLONASS in some
        #   cycles and after GLONASS in others, so check values and determine which should go first
        sentence1_sv_ids = [int(id_) for id_ in merge_group[0].sentence.data[2:14] if id_ != '']

        glonass_ids = range(65, 96 + 1)
        # If there are GLONASS SV IDs in the first sentence, switch them
        if len(set(sentence1_sv_ids) & set(glonass_ids)):
            merge_group = [merge_group[1], merge_group[0]]

        # Merge data from sentences
        data = merge_group[0].sentence.data[:-3] + merge_group[1].sentence.data[2:]

        sentence = Sentence(talker, sentence_type, fields, data)

        # call __init__ of base class
        super().__init__(sentence, merge_group[0].date_time)

        self.cycle_id = merge_group[0].cycle_id
        self.datetime_is_interpolated = False
        self.sentence_is_merged_from_multiple = True

    def __str__(self):
        return str(self.cycle_id) + ' ' + str(self.sentence.talker) + ' ' + str(self.sentence.sentence_type) + ' ' + str(self.sentence.data) + ' ' + str(self.date_time)


def parse_and_validate_args(passed_args):
    parser = argparse.ArgumentParser()
    parser.add_argument("filepath",
                        help="file system path to file containing NMEA data")
    parser.add_argument("output_method",
                        choices=['csv', 'db', 'both'],
                        help="Where to output data: CSV files, database, or both")
    parser.add_argument("--cycle_start", "-cs",
                        help="Talker+sentence_type, e.g. 'GNRMC', used to key off of for sentence merging and more; "
                             "must appear once and only once in each cycle, and must be at the beginning of each cycle; "
                             "must contain date and time information for sentences to be datetime stamped")
    parser.add_argument("--num_sentences_per_cycle", "-spc",  # Requirement for this is enforced in assign_cycle_ids()
                        type=int,
                        help="If the cycle_start argument is not provided, and sentences are not all of type GSV, "
                             "cycles will be inferred from this argument. Every num_sentences_per_cycle will be given "
                             "the same cycle_id starting with the first sentence. Sentence merging is based on cycle_id.")
    parser.add_argument("--backfill_datetimes", "-bfdt",
                        action="store_true",
                        help="Backfill datetimes where missing by extrapolating/interpolating from messages "
                             "that do have datetime information")
    parser.add_argument("--drop_previous_db_tables", "-dropt",
                        action="store_true",
                        help="Drop all previous DB tables before importing new data; only applies when output_method is 'db' or 'both'")
    parser.add_argument("--unique_id", "-uid",
                        type=str,
                        default=None,
                        help="A unique ID that will be added as a column in all database tables and CSV output files;"
                             " allows this dataset to be distinguished from other datasets when they are stored together")

    args = parser.parse_args(passed_args)

    # Check if input file exists
    if not os.path.isfile(args.filepath):
        sys.exit(f"\nERROR: File '{args.filepath}' does not exist.\n\nExiting.\n")

    # Check if num_sentences_per_cycle value is valid
    if args.num_sentences_per_cycle is not None:
        args.num_sentences_per_cycle = int(args.num_sentences_per_cycle)
        if args.num_sentences_per_cycle < 1:
            sys.exit(f"\nERROR: num_sentences_per_cycle argument '{args.num_sentences_per_cycle}' is invalid. Must be a positive "
                     "integer greater than 0.\n\nExiting.\n")

    return args


def open_file(filepath):
    return open(filepath, encoding='utf-8')


def read_file(file):
    sentences = []

    for line_idx, line in enumerate(file.readlines()):
        try:
            sentence = pynmea2.parse(line)

            # Some GSA sentences contain a 'data' item after 'pdop', 'hdop', 'vdop'
            # This item is not present in the 'fields' list of the NMEA object, but is present
            #   in the 'data' list. This causes indexing problems when expanding GSA sentences for merging.
            # In fact if 'data' contains more items than 'fields', there will always be indexing problems.
            # So truncate the last items of 'data' until its length is equal to 'fields'.
            if len(sentence.data) > len(sentence.fields):
                sentence.data = sentence.data[:len(sentence.fields)]

            sentences.append(sentence)
        except pynmea2.ParseError as ex:
            print(f'Parse error on line {line_idx + 1}: {ex}')
            continue

    if len(sentences) == 0:
        sys.exit(f"\nNo data found in {file.name} input file.\nExiting.\n\n")

    return sentences


def categorize_sentences(sentences: list[DateTimeStampedSentence]):
    # Make a list of all sentence types
    sentence_types: list[str] = []
    for dts_sentence in sentences:
        if get_sentence_type(dts_sentence.sentence) not in sentence_types:
            sentence_types.append(get_sentence_type(dts_sentence.sentence))

    # Create a list of sentence sets (a separate list for each sentence type)
    sentence_sets: list[list[DateTimeStampedSentence]] = [[] for _ in range(len(sentence_types))]
    for dts_sentence in sentences:
        type_idx = sentence_types.index(get_sentence_type(dts_sentence.sentence))
        # Add each sentence to the appropriate list
        sentence_sets[type_idx].append(dts_sentence)

    return sentence_sets


# Look for the beginning of cycles, get the timestamp for each cycle,
#   pair that timestamp with each sentence from the cycle
# This function assumes that the sentence that starts the cycle contains a date and time stamp
#   which may only be true for RMC sentences
def datetime_stamp_sentences(sentences: list, cycle_start='GNRMC'):
    datetime_stamped_sentences: list[DateTimeStampedSentence] = []

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

            if date and time:
                # Sentence contains both date and time
                date_time = datetime.combine(date, time)

        datetime_stamped_sentence = DateTimeStampedSentence(sentence, date_time)
        datetime_stamped_sentences.append(datetime_stamped_sentence)

    return datetime_stamped_sentences


# To properly assign cycle IDs, the cycle_start talker+sentence_type must appear once and only once in each cycle
def assign_cycle_ids(dts_sentences: list[DateTimeStampedSentence], args: argparse.Namespace):
    # TODO: Check database for highest cycle_id and start there so that IDs will be unique across runs of this script

    cycle_start = args.cycle_start
    if not cycle_start:
        cycle_start = 'GNRMC'

    unique_talker_and_type_pairs = set([dts_sentence.sentence.talker + dts_sentence.sentence.sentence_type for dts_sentence in dts_sentences])

    if cycle_start in unique_talker_and_type_pairs:  # If sentences contain cycle_start sentences
        cycle_id = -1
        for sen_idx, dts_sentence in enumerate(dts_sentences):
            if dts_sentence.sentence.talker + dts_sentence.sentence.sentence_type == cycle_start:
                cycle_id += 1
            dts_sentences[sen_idx].cycle_id = cycle_id

    # If sentences are exclusively 'GPGSV' xor 'GLGSV' xor 'GAGSV' sentences
    elif (len(unique_talker_and_type_pairs) == 1 and (('GPGSV' in unique_talker_and_type_pairs) or ('GLGSV' in unique_talker_and_type_pairs) or ('GAGSV' in unique_talker_and_type_pairs))):
        cycle_id = -1
        for sen_idx, dts_sentence in enumerate(dts_sentences):
            if int(dts_sentence.sentence.msg_num) == 1:
                cycle_id += 1
            dts_sentences[sen_idx].cycle_id = cycle_id

    else:
        num_sentences_per_cycle = args.num_sentences_per_cycle
        if num_sentences_per_cycle is None:
            sys.exit("\n\nERROR: If an argument for cycle_start is not provided or is not valid, and sentences are not exclusively "
                     "GPGSVV xor GLGSV xor GAGS sentences, then the num_sentences_per_cycle argument must be provided.\n\nExiting.\n")
        cycle_id = -1
        cycle_start_idxs = range(0, len(dts_sentences), num_sentences_per_cycle)
        for sen_idx, dts_sentence in enumerate(dts_sentences):
            if sen_idx in cycle_start_idxs:
                cycle_id += 1
            dts_sentences[sen_idx].cycle_id = cycle_id

    return dts_sentences


# For sentences from a particular sentence_set (particular talker), if there are sentences of the same sentence_type
#   from the same cycle, merge them into one sentence
def merge_groups(sentence_sets: list[list[DateTimeStampedSentence]]):
    for set_idx, sentence_set in enumerate(sentence_sets):
        sentence_type = sentence_set[0].sentence.sentence_type

        # These are the supported sentence types that can be merged
        if sentence_type in ['GSV', 'GSA']:
            cycle_ids = [dts_sentence.cycle_id for dts_sentence in sentence_set]

            # Keep unique cycle IDs only by converting to set and back to list
            cycle_ids = list(set(cycle_ids))

            sentences_merged = []

            for cycle_id in cycle_ids:
                merge_group_sentences = [dts_sentence for dts_sentence in sentence_set if dts_sentence.cycle_id == cycle_id]

                if len(merge_group_sentences) > 1:
                    if sentence_type == 'GSV':
                        merged_sentence = MergedSentence_GSV(merge_group_sentences)

                    if sentence_type == 'GSA':
                        merged_sentence = MergedSentence_GSA(merge_group_sentences)

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
def backfill_datetimes(sentence_dfs: list[pd.DataFrame], verbose=False):
    # Make sure sentences are in order by cycle, they may have gotten out of order when merged
    sentence_dfs = sort_dfs(sentence_dfs, sort_by='cycle_id')

    # Find time delta (interval) between sentence cyles
    interval = None
    for df in sentence_dfs:
        if not interval:
            for sen_idx, _ in enumerate(df['datetime']):
                # If this dts sentence and the next have valid datetimes
                if (df['datetime'][sen_idx] and sen_idx + 1 < len(df['datetime']) - 1 and df['datetime'][sen_idx + 1] and df['cycle_id'][sen_idx] < df['cycle_id'][sen_idx + 1]):
                    first_datetime = df['datetime'][sen_idx]
                    second_datetime = df['datetime'][sen_idx + 1]
                    interval = second_datetime - first_datetime

                    # Don't look at sentences of same type in same cycle (interval will be 0)
                    if interval.total_seconds() > 0:
                        break
                    else:
                        interval = None

    if not interval:
        if verbose:
            print("\n  Time delta between sentence cycles could not be determined, so datetimes will not be backfilled.")
        return

    # Suppress chained_assignment warnings, default='warn'
    pd.options.mode.chained_assignment = None  # type: ignore
    # See https://pandas.pydata.org/pandas-docs/stable/user_guide/indexing.html#returning-a-view-versus-a-copy
    # TODO: Investigate how to do this better and remove this warning suppression

    for df_idx, df in enumerate(sentence_dfs):
        # Find sentences without datetime value
        datetime_bools = df['datetime'].isnull()
        no_datetime_idxs = datetime_bools[datetime_bools].index.tolist()

        # Find first sentence in this dataframe with datetime
        first_datetime_idx = (~datetime_bools).idxmax()

        # Get lists of indices to process
        no_datetime_idxs_preceding = [idx for idx in no_datetime_idxs if idx < first_datetime_idx]
        no_datetime_idxs_succeeding = [idx for idx in no_datetime_idxs if idx > first_datetime_idx]

        # From first sentence with datetime, fill in preceding sentences moving backwards
        no_datetime_idxs_preceding.reverse()
        for sen_idx in no_datetime_idxs_preceding:
            # If sentence is of same talker+sentence_type and different cycle
            if df['cycle_id'][sen_idx] < df['cycle_id'][sen_idx + 1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx + 1] - interval
            # If sentence is of same talker+sentence_type and same cycle
            if df['cycle_id'][sen_idx] == df['cycle_id'][sen_idx + 1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx + 1]

            df['datetime_is_interpolated'][sen_idx] = True

        # Fill in succeeding sentences' datetimes
        for sen_idx in no_datetime_idxs_succeeding:
            # If sentence is of same talker+sentence_type and different cycle
            if df['cycle_id'][sen_idx] > df['cycle_id'][sen_idx - 1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx - 1] + interval
            # If sentence is of same talker+sentence_type and same cycle
            if df['cycle_id'][sen_idx] == df['cycle_id'][sen_idx - 1]:
                df['datetime'][sen_idx] = df['datetime'][sen_idx - 1]

            df['datetime_is_interpolated'][sen_idx] = True


# Derive custom data from NMEA data
def derive_data(sentence_dfs: list[pd.DataFrame]):
    for df in sentence_dfs:
        if df['sentence_type'][0] == 'GNS':
            df['mode_indicator_gps'] = df.apply(lambda row: get_position_mode(row['mode_indicator'], 'GPS'), axis=1)
            df['mode_indicator_glonass'] = df.apply(lambda row: get_position_mode(row['mode_indicator'], 'GLONASS'), axis=1)
            df['mode_indicator_galileo'] = df.apply(lambda row: get_position_mode(row['mode_indicator'], 'Galileo'), axis=1)
            df['mode_indicator_beidou'] = df.apply(lambda row: get_position_mode(row['mode_indicator'], 'BeiDou'), axis=1)


def get_coordinate(coord: str, coord_dir: str, coord_type: str):
    # 'lat' is in  DDMM.MMMMM format, number of decimal places is variable
    # 'lon' is in DDDMM.MMMMM format, number of decimal places is variable

    # If is NaN
    if coord != coord:
        return coord

    if coord_type == 'lat':
        degree = float(coord[:2])
        minute = float(coord[2:])
    if coord_type == 'lon':
        degree = float(coord[:3])
        minute = float(coord[3:])

    coord_f = degree + minute / 60

    if (coord_dir == 'S' or coord_dir == 'W'):
        coord_f = -coord_f

    return coord_f


def get_position_mode(mode_indicator: str, constellation: str):
    if constellation == 'GPS':
        return mode_indicator[0]

    if constellation == 'GLONASS':
        if len(mode_indicator) > 1:
            return mode_indicator[1]

    if constellation == 'Galileo':
        if len(mode_indicator) > 2:
            return mode_indicator[2]

    if constellation == 'BeiDou':
        if len(mode_indicator) > 3:
            return mode_indicator[3]

    return '?'


def add_uid_to_dfs(sentence_dfs: list[pd.DataFrame], unique_id):
    for df in sentence_dfs:
        # Insert the unique ID as the first column
        df.insert(0, 'unique_id', unique_id)


def sentences_to_dataframes(sentence_sets: list[list[DateTimeStampedSentence]]):
    dfs: list[pd.DataFrame] = []

    for set_idx, sentence_set in enumerate(sentence_sets):
        sentence_type = sentence_sets[set_idx][0].sentence.sentence_type
        sentence_is_merged = sentence_sets[set_idx][0].sentence_is_merged_from_multiple

        fields = sentence_sets[set_idx][0].sentence.fields

        # If first sentence is not a merged sentence, make sure that fields allow for merged sentences
        if (sentence_type == 'GSV' and not sentence_is_merged):
            fields = expand_GSV_fields(fields)
        elif (sentence_type == 'GSA' and not sentence_is_merged):
            fields = expand_GSA_fields(fields)
        columns = [column_tuple[1] for column_tuple in fields]

        # Add columns for data fields missing from class
        # TODO: Fork pynmea2 module to correct
        # Issure reported here: https://github.com/Knio/pynmea2/issues/118
        if sentence_type == 'RMC':
            columns.append('mode')

        # Add columns for latitude and longitude if type is RMC or GGA, because these pynmea2
        #   sentence objects have parameters containing the calculated values already
        if sentence_type in ['RMC', 'GGA']:
            columns.append('latitude')
            columns.append('longitude')

        columns.insert(0, 'cycle_id')
        columns.insert(1, 'datetime')
        columns.insert(2, 'datetime_is_interpolated')
        columns.insert(3, 'sentence_is_merged_from_multiple')
        columns.insert(4, 'talker')
        columns.insert(5, 'sentence_type')

        list_of_data_rows = []

        for dts_sentence in sentence_set:
            row_data: list = dts_sentence.sentence.data.copy()

            date_time = dts_sentence.date_time
            row_data.insert(0, dts_sentence.cycle_id)
            row_data.insert(1, date_time)
            row_data.insert(2, dts_sentence.datetime_is_interpolated)
            row_data.insert(3, dts_sentence.sentence_is_merged_from_multiple)
            row_data.insert(4, dts_sentence.sentence.talker)
            row_data.insert(5, dts_sentence.sentence.sentence_type)

            # For GSV sentences with less data than others, fill with NaNs where there is no data
            if sentence_type == 'GSV':
                placeholders = [np.NaN] * (len(columns) - len(row_data))
                row_data = row_data + placeholders

            # For non-merged GSA sentences with less data than merged sentences, fill with NaNs where there is no data
            if (sentence_type == 'GSA' and not sentence_is_merged):
                placeholders = [np.NaN] * (len(columns) - len(row_data))

                # Make sure SV ID data gets put in correct (GP vs GL) columns
                sv_ids_in_sentence = row_data[8:20]

                # See notes in MergedSentence_GSA class
                glonass_ids = range(65, 96 + 1)

                # Row data consists of: 6 elements inserted above, 2 elements, 12 SV IDs, 3 elements
                # Columns/fields consist of: 6 elements inserted above, 2 elements, 12 GP SV IDs, 12 GL SV IDs, 3 elements
                if len(set(sv_ids_in_sentence) & set(glonass_ids)):
                    # If there are GLONASS SV IDs in the sentence
                    row_data = row_data[:-15] + placeholders + row_data[-15:]
                else:
                    row_data = row_data[:-3] + placeholders + row_data[-3:]

            # For RMC and GGA sentences with less data than others, fill with NaNs where there is no data
            # Also add the already calculated latitude and longitude
            if sentence_type in ['RMC', 'GGA']:
                placeholders = [np.NaN] * (len(columns) - len(row_data))
                row_data = row_data + placeholders

                # set latitude and longitude
                row_data = row_data[:-2] + [dts_sentence.sentence.latitude, dts_sentence.sentence.longitude]

            list_of_data_rows.append(row_data)

        df = pd.DataFrame(list_of_data_rows, columns=columns)

        dfs.append(df)

    pd.set_option('display.max_rows', None)
    # pd.set_option('display.max_columns', None)
    # pd.set_option('display.width', 180)

    # Corrrect data types of columns
    dfs = [correct_data_types(df) for df in dfs]

    return dfs


def sort_dfs(dfs: list[pd.DataFrame], sort_by='cycle_id', ascending=True):
    for df_idx, _ in enumerate(dfs):
        dfs[df_idx] = dfs[df_idx].sort_values(sort_by, ascending=ascending)
        dfs[df_idx] = dfs[df_idx].reset_index(drop=True)

    return dfs


def correct_data_types(df: pd.DataFrame):
    # Do this replace first because pd.Nat won't be replaced with np.NaN
    df.replace(to_replace=pd.NaT, value='', inplace=True)
    df.replace(to_replace='', value=np.NaN, inplace=True)

    # Cast dataframe data from strings to appropriate datatypes specified in columns_to_cast.py
    # sentence_type = df['sentence_type'][0]
    # for py_datatype in datatype_dict.keys():
    #     # If key exists in dictionary
    #     if (sentence_type, py_datatype) in columns_to_cast:
    #         for column in columns_to_cast[sentence_type, py_datatype]:
    #             df[column] = df[column].astype('float').astype(py_datatype)
    #             # Cast as float first to get around bug: https://stackoverflow.com/questions/60024262/error-converting-object-string-to-int32-typeerror-object-cannot-be-converted

    # Needed for backfill_datetimes() to work properly
    df['datetime'].replace(to_replace=np.NaN, value=pd.NaT, inplace=True)  # type: ignore

    return df


def dfs_to_csv(sentence_dfs: list[pd.DataFrame], input_file_path, verbose=False):
    input_file_name = os.path.basename(input_file_path)
    input_file_name = os.path.splitext(input_file_name)[0]

    for df_idx, df in enumerate(sentence_dfs):
        filename = f"{input_file_name}_{df['talker'][0]}{df['sentence_type'][0]}.csv"
        df.to_csv(filename, index=False)  # Save to cwd

        if verbose:
            # If this is the first df
            if df_idx == 0:
                print(f"data from logfile '{input_file_path}' written to:")
            print("  " + filename)


def dfs_to_db(sentence_dfs: list[pd.DataFrame], input_file_path, verbose=False):
    table_name_base = 'nmea'

    # Pass lowercase 'talker_sentencetype' as table name suffixes
    table_name_suffixes = [f"{df['talker'][0]}_{df['sentence_type'][0]}".lower() for df in sentence_dfs]

    # Construct a dictionary of database datatypes for each column to import, using columns_to_cast
    for df in sentence_dfs:
        sentence_type = df['sentence_type'][0]
        for py_datatype, _ in datatype_dict.items():
            # If key exists in dictionary
            if (sentence_type, py_datatype) in columns_to_cast:
                for column in columns_to_cast[sentence_type, py_datatype]:
                    # Get database datatype for column
                    db_datatypes[column] = datatype_dict[py_datatype]

    table_names = db_data_import.send_data_to_db(sentence_dfs, table_name_base, table_name_suffixes, dtypes=db_datatypes)

    if verbose:
        print(f"data from logfile '{input_file_path}' written to:")
        for table_name in table_names:
            print(f"  '{table_name}' table in '{db_creds.DB_NAME}' database")


def get_sentence_type(sentence) -> str:
    return sentence.talker + sentence.sentence_type


# Add fields for SVs 5-16. See the Development Notes/Oddities section of README.md
def expand_GSV_fields(fields: tuple[tuple[str, str]]):
    # Make mutable
    fields_ = list(fields)

    # Original GSV sentence supports 0-4 SVs, so copy and change fields for SV 4
    fields_to_duplicate = [field for field in fields_ if field[0].endswith('4')]

    for SV_idx in range(5, 16 + 1):
        new_fields = [(re.sub(r'4$', str(SV_idx), field[0]), re.sub(r'4$', str(SV_idx), field[1])) for field in fields_to_duplicate]
        fields_ = fields_ + new_fields

    # Return to original immutable tuple state
    fields = tuple(fields_)

    return fields


# Create additional sv_id01...sv_id12 fields for second constellation, and label prefix with 'gp' for GPS, 'gl' for GLONASS and 'ga' for Galileo
def expand_GSA_fields(fields: tuple[tuple[str, str]]):
    # Make mutable
    fields_ = list(fields)

    fields_to_duplicate = [field for field in fields_ if field[1].startswith('sv_id')]
    gp_fields = [('GP ' + field[0], 'gp_' + field[1]) for field in fields_to_duplicate]
    gl_fields = [('GL ' + field[0], 'gl_' + field[1]) for field in fields_to_duplicate]
    ga_fields = [('GA ' + field[0], 'ga_' + field[1]) for field in fields_to_duplicate]

    # Keep first two fields and last three fields, replacing what is in between
    fields_ = fields_[:2] + gp_fields + gl_fields + ga_fields + fields_[-3:]

    # Return to original immutable tuple state
    fields = tuple(fields_)

    return fields


# Do data processing that we will always want to do
def process_data_common(sentences: list, args: argparse.Namespace):
    dts_sentences = datetime_stamp_sentences(sentences, args.cycle_start)
    # 'dts' -> 'datetime stamped'
    dts_sentences = assign_cycle_ids(dts_sentences, args)
    sentence_sets = categorize_sentences(dts_sentences)
    sentence_sets = merge_groups(sentence_sets)
    sentence_dfs = sentences_to_dataframes(sentence_sets)

    return sentence_dfs


def main(passed_args=None):
    args = parse_and_validate_args(passed_args)

    print("\nReading in data... ", end="")
    file = open_file(args.filepath)
    sentences = read_file(file)
    print("done.")

    print("\nProcessing data... ", end="")
    sentence_dfs = process_data_common(sentences, args)  # Cycle starts with 'GNRMC' sentence
    if args.backfill_datetimes:
        backfill_datetimes(sentence_dfs, verbose=True)
    derive_data(sentence_dfs)
    add_uid_to_dfs(sentence_dfs, args.unique_id)
    print("done.")

    if (args.output_method == 'csv' or args.output_method == 'both'):
        print("\nWriting data to CSVs... ", end="")
        dfs_to_csv(sentence_dfs, args.filepath, verbose=True)
        print("done.")

    if (args.output_method == 'db' or args.output_method == 'both'):
        if args.drop_previous_db_tables:
            print()
            db_utils.drop_db_tables(db_table_lists.nmea_tables, verbose=True)

        print("\nWriting data to database... ", end="")
        dfs_to_db(sentence_dfs, args.filepath, verbose=True)
        print("done.")

    print("\nAll done. Exiting.\n\n")


if __name__ == '__main__':
    main()
