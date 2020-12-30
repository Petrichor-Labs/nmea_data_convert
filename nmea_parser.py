import pynmea2
import argparse
import sys
import os
from datetime import datetime
import pandas as pd
from collections import namedtuple
import re
import functools
print = functools.partial(print, flush=True)

def parse_and_validate_args():

    parser = argparse.ArgumentParser()
    parser.add_argument("filepath", help="File system path to file containing NMEA data")
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
def datetime_stamp_sentences(sentences, cycle_start='RMC'):

    datetime_stamped_sentences = []

    # Set all datetimes to 
    date_time = pd.NaT  # NaT -> 'Not a Time', essentiall a NaN/Null value

    for sentence in sentences:

        # TODO: Search through cycle to find sentence(s) containing date and/or time

        # If sentence is the first in a cycle, get the timestamp 
        if sentence.sentence_type == cycle_start:
            
            if hasattr(sentence, 'timestamp'):
                time = sentence.timestamp
            else:
                time = None
            
            if hasattr(sentence, 'datestamp'):
                date = sentence.datestamp
            else:
                date = None
            
            if date and time:
                date_time = datetime.combine(date, time)
            else:  # Sentence does not contain date and time
                date_time = pd.NaT  # NaT -> 'Not a Time', essentiall a NaN/Null value

        datetime_stamped_sentence = DateTimeStampedSentence(sentence, date_time)
        datetime_stamped_sentences.append(datetime_stamped_sentence)

    return datetime_stamped_sentences


# Get list of groups (lists) of sentences that should be merged together
# Sentences to be merged are those that have the same type and that are (assumed to be) 
#   part of the same cycle (e.g., msg_num 1 or 2 out of num_messages 2) and where the date and time match
# Assumes sentences that should be merged are listed together but in no particular order
# Currently only supporting merging GSV sentences
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
            for merge_group in set_merge_group_list:

                if len(merge_group) > 1:  # There will be some empty sets, but we want a s
                    merge_group_sentences = [sentence_sets[set_idx][sen_idx] for sen_idx in merge_group ]
                    merged_sentence = MergedSentence_GSV(merge_group_sentences)
                    sentence_sets[set_idx].append(merged_sentence)

    return sentence_sets


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
        if sentence_sets[set_idx][0].sentence.sentence_type == 'RMC':
            columns.append('mode')

        columns.insert(0, 'datetime')
        columns.insert(0, 'talker')
        columns.insert(0, 'sentence_type')

        df = pd.DataFrame(columns=columns)

        for dts_sentence in sentence_set:

            row_data = dts_sentence.sentence.data.copy()

            if isinstance(dts_sentence.date_time, pd._libs.tslibs.nattype.NaTType):
                date_time = ''
            else:
                date_time = dts_sentence.date_time
            row_data.insert(0, date_time)
            row_data.insert(0, dts_sentence.sentence.talker)
            row_data.insert(0, dts_sentence.sentence.sentence_type)

            # Single GSV sentences have data for 4 SVs and merged GSV sentences have data for 12 SVs, so fill single GSV sentences with NaNs for SV 5-12 data
            if dts_sentence.sentence.sentence_type == 'GSV':
                placeholders = ['']  * (len(columns) - len(row_data))
                row_data = row_data + placeholders

            df.loc[len(df)] = row_data  # Append data as new row in dataframe
            
        dfs.append(df)

    # pd.set_option('display.max_rows', None)
    # pd.set_option('display.max_columns', None)
    # pd.set_option('display.width', 180)

    return dfs


def dfs_to_csv(sentence_dfs, input_file_path, verbose=False):

    input_file_name = os.path.basename(input_file_path)
    input_file_name = os.path.splitext(input_file_name)[0]

    for df_idx, df in enumerate(sentence_dfs):
        filename = f"{input_file_name}_{df['talker'][0]}{df['sentence_type'][0]}.csv"
        df.to_csv(filename, index=False)  # Save to cwd

        if verbose:
            if df_idx is 0:  # If this is the first df
                print("data written to:")
            print("  " + filename)

def get_sentence_type(sentence):

    return sentence.talker + sentence.sentence_type


class DateTimeStampedSentence:

    def __init__(self, sentence, date_time):

        # TODO: Check if inputs are of correct types (use isinstance())
        # https://stackoverflow.com/questions/14570802/python-check-if-object-is-instance-of-any-class-from-a-certain-module

        self.sentence = sentence
        self.date_time = date_time

    def __str__(self):

        return str(self.sentence) + ' ' + str(self.date_time)


class MergedSentence_GSV:

    def __init__(self, merge_group):
        
        self.date_time = merge_group[0].date_time

        Sentence = namedtuple('sentence', 'talker sentence_type fields data')
        
        talker        = merge_group[0].sentence.talker
        sentence_type = merge_group[0].sentence.sentence_type

        # Add fields for SVs 5-12. 12 SVs seems to be a common number of maximum supported SVs for GNSS devices
        fields = expand_GSV_fields(merge_group[0].sentence.fields)        

        # Merge SV data from sentences after the first with the data from the first sentences
        data = merge_group[0].sentence.data
        data[1] = '-1'  # msg_num doesn't apply to merged sentence, so set to NaN flag
        for dts_sentence in merge_group[1:]:
            data = data + dts_sentence.sentence.data[3:]

        self.sentence = Sentence(talker, sentence_type, fields, data)   


# Add fields for SVs 5-12. 12 SVs seems to be a common number of maximum supported SVs for GNSS devices
def expand_GSV_fields(fields):

    fields = list(fields)  # Make mutable
    fields_to_duplicate = [field for field in fields if field[0].endswith('4')]  # Original GSV sentence supports 0-4 SVs, so copy and change fields for SV 4
    for SV_idx in range(4, 12+1):
        new_fields = [(re.sub(r'4$', str(SV_idx), field[0]), re.sub(r'4$', str(SV_idx), field[1])) for field in fields_to_duplicate]
        fields = fields + new_fields
    fields = tuple(fields)  # Return to original immutable tuple state

    return fields


def main():

    print("\nReading in data... ", end="")
    args = parse_and_validate_args()
    file = open_file(args.filepath)
    sentences = read_file(file)
    print("done.")
    
    print("\nProcessing data... ", end="")
    dts_sentences = datetime_stamp_sentences(sentences, 'RMC')  # Cycle starts with 'RMC' sentence
        # 'dts' -> 'datetime stamped'
    sentence_sets = categorize_sentences(dts_sentences)
    merge_group_lists = get_merge_groups(sentence_sets)
    sentence_sets = merge_groups(sentence_sets, merge_group_lists)
    sentence_dfs  = sentences_to_dataframes(sentence_sets)
    print("done.")
    
    print("\nWriting data to CSVs... ", end="")
    dfs_to_csv(sentence_dfs, args.filepath, verbose=True)
    print("done.")

    print("\nAll done. Exiting.\n\n")

if __name__ == '__main__':

    main()
