import pynmea2
import argparse
import os
from datetime import datetime
import pandas as pd

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

    for line in file.readlines():
        try:
            sentence = pynmea2.parse(line)
            sentences.append(sentence)
        except pynmea2.ParseError as e:
            print('Parse error: {}'.format(e))
            continue

    return sentences


def sort_sentences(sentences):

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

    for sentence in sentences:

        # TODO: Search through cycle to find sentence(s) containing date and/or time

        # If sentence is the first in a cycle, get the timestamp 
        if sentence.sentence_type == cycle_start:
            time = sentence.timestamp
            date = sentence.datestamp
            if date and time:
                date_time = datetime.combine(date, time)
            else:  # Sentence does not contain date and time
                date_time = pd.NaT  # NaT -> 'Not a Time', essentiall a NaN/Null value

        datetime_stamped_sentence = DateTimeStampedSentence(sentence, date_time)
        datetime_stamped_sentences.append(datetime_stamped_sentence)

    return datetime_stamped_sentences


# Merge sentences that have the same type and that are (assumed to be) 
#   part of the same cycle (e.g., msg_num 1 or 2 out of num_messages 2)
def merge_sentence_groups(sentence_sets):

    for sentence_set in sentence_sets:
        for dts_sentence in sentence_set:

            print(dts_sentence)

    return sentences


def sentences_to_dataframes(sentences):

    return sentences


def dfs_to_csv(sentence_dfs):

    pass


def get_sentence_type(sentence):

    return sentence.talker + sentence.sentence_type


def print_sentences(sentences):

    for sentence in sentences:
        print(type(sentence))
        print(sentence)
        print(type(repr(sentence)))
        print(repr(sentence))
        print(type(sentence.data))
        print(sentence.data)
        print()
        print(sentence.fields)
        print()
        print(sentence.__dict__)
        print()
        print()
        print()


class DateTimeStampedSentence:

    def __init__(self, sentence, date_time):

        # TODO: Check if inputs are of correct types (use isinstance())
        # https://stackoverflow.com/questions/14570802/python-check-if-object-is-instance-of-any-class-from-a-certain-module

        self.sentence = sentence
        self.date_time = date_time

    def __str__(self):

        return str(self.sentence) + ' ' + str(self.date_time)


if __name__ == '__main__':

    args = parse_and_validate_args()

    file = open_file(args.filepath)
    sentences = read_file(file)
    # print_sentences(sentences)
    datetime_stamped_sentences = datetime_stamp_sentences(sentences, 'RMC')  # Cycle starts with 'RMC' sentence
    
    dts_sentences = datetime_stamped_sentences  # Alias/rename variable
    del datetime_stamped_sentences

    sentence_sets = sort_sentences(dts_sentences)
    sentence_sets = merge_sentence_groups(sentence_sets)
    sentence_dfs  = sentences_to_dataframes(sentences)
    dfs_to_csv(sentence_dfs)

