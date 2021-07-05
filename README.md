This library makes use of [pynmea2](https://github.com/Knio/pynmea2) to parse through input NMEA 0183 data, organize it, and output it to CSV files or to a PostgreSQL database.

## Terminology
* **`sentence`**:
A line from your data file from a particular `talker` and of a particular `sentence_type` E.g.:
`$GNRMC,,V,,,,,,,,,,N*4D`
`$GNGGA,045824.00,3944.54025,N,10511.64604,W,1,03,4.93,1784.2,M,-21.5,M,,*49`

* **`talker`**:
The type of the transmitting unit. For the purposes of satellite navigation, this is the constellation from which data is being received.
E.g.: `GA`: Galileo Positioning System; `GB`: BDS (BeiDou System); `GL`: GLONASS Receiver; `GN`: Global Navigation Satellite System (GNSS); `GP`: Global Positioning System (GPS)
See: https://gpsd.gitlab.io/gpsd/NMEA.html#_talker_ids, or https://www.nmea.org/Assets/20190303%20nmea%200183%20talker%20identifier%20mnemonics.pdf

* **`sentence_type`**:
One of several types of NMEA sentences that can be received from the talker.
E.g.: `RMC`, `VTG`, `GGA`, `GSA`, `GSV`, `GLL`
See: https://gpsd.gitlab.io/gpsd/NMEA.html#_nmea_standard_sentences

## Setup

Input data files can contain either sentences having all the same `talker`+`sentence_type`, like that of `test_data/test_data_0_GLGSV.nmea`, `test_data_0_GNGGA.nmea`, etc., or cycles of sentences like that of `test_data/test_data_0_all.nmea`. Your input file should have a format similiar to those under `test_data`.

To have your data datetime stamped, it must be in a format like that of `test_data/test_data_0_all.nmea`, with RMC sentences containing date and time stamps proceeding other sentences in the same cycle. 

Useage of the `cycle_start` (`cs`), `num_sentences_per_cycle` (`spc`), and `backfill_datetimes` (`bfdt`) parameters will depend on the format of your data, and some combination of them is required. See below for examples. See the Usage section for explanations of the parameters.


If working with a database, the database access information/credentials must be setup in `db_creds.py`.


## Usage
```
$ cd nmea_data_convert/
$ pip install -r requirements.txt 
...
$ python nmea_data_convert.py --help
usage: nmea_data_convert.py [-h] [--cycle_start CYCLE_START] [--num_sentences_per_cycle NUM_SENTENCES_PER_CYCLE] [--backfill_datetimes] [--drop_previous_db_tables] filepath {csv,db,both}

positional arguments:
  filepath              file system path to file containing NMEA data
  {csv,db,both}         where to output data: CSV files, database, or both

optional arguments:
  -h, --help            show this help message and exit
  --cycle_start CYCLE_START, --cs CYCLE_START
                        talker+sentence_type, e.g. 'GNRMC'; used to key off of for sentence merging, and more; must appear once and only once in each cycle, and must be at the beginning of each cycle; must contain date and time information for sentences to be datetime
                        stamped
  --num_sentences_per_cycle NUM_SENTENCES_PER_CYCLE, --spc NUM_SENTENCES_PER_CYCLE
                        If the cycle_start argument is not provided, and sentences are not all of type GSV, cycles will be inferred from this argument. Every num_sentences_per_cycle will be given the same cycle_id starting with the first sentence. Sentence merging is
                        based on cycle_id.
  --backfill_datetimes, --bfdt
                        backfill datetimes where missing by extrapolating from messages with datetime information
  --drop_previous_db_tables, --dropt
                        drop all previous DB tables before importing new data; only applies when output_method is 'db' or 'both'
```
## Examples
### Example 1
Output cycles of NMEA sentences to CSV files using GNRMC sentences as the cycle start:
```
$ ls -l *.csv
ls: *.csv: No such file or directory
$ python nmea_data_convert.py test_data/test_data_0_all.nmea csv --cs GNRMC

Reading in data... done.

Processing data... done.

Writing data to CSVs... data from logfile 'test_data/test_data_0_all.nmea' written to:
  test_data_0_all_GNRMC.csv
  test_data_0_all_GNVTG.csv
  test_data_0_all_GNGGA.csv
  test_data_0_all_GNGSA.csv
  test_data_0_all_GPGSV.csv
  test_data_0_all_GLGSV.csv
  test_data_0_all_GNGLL.csv
done.

All done. Exiting.


MacBook-Pro-4:nmea_data_convert Thomas$ ls -l *.csv
-rw-r--r--  1 Thomas  staff  16166 Jan 17 16:55 test_data_0_all_GLGSV.csv
-rw-r--r--  1 Thomas  staff  12067 Jan 17 16:55 test_data_0_all_GNGGA.csv
-rw-r--r--  1 Thomas  staff   9401 Jan 17 16:55 test_data_0_all_GNGLL.csv
-rw-r--r--  1 Thomas  staff  14136 Jan 17 16:55 test_data_0_all_GNGSA.csv
-rw-r--r--  1 Thomas  staff  12536 Jan 17 16:55 test_data_0_all_GNRMC.csv
-rw-r--r--  1 Thomas  staff   8344 Jan 17 16:55 test_data_0_all_GNVTG.csv
-rw-r--r--  1 Thomas  staff  20698 Jan 17 16:55 test_data_0_all_GPGSV.csv
```

### Example 2
Output cycles of NMEA sentences to both CSV files and database using GNRMC sentences as the cycle start, backfill datetimes, and drop previous tables from database:
```
$ python nmea_data_convert.py test_data/test_data_0_all.nmea both --bfdt --dropt --cs GNRMC

Reading in data... done.

Processing data... done.

Writing data to CSVs... data from logfile 'test_data/test_data_0_all.nmea' written to:
  test_data_0_all_GNRMC.csv
  test_data_0_all_GNVTG.csv
  test_data_0_all_GNGGA.csv
  test_data_0_all_GNGSA.csv
  test_data_0_all_GPGSV.csv
  test_data_0_all_GLGSV.csv
  test_data_0_all_GNGLL.csv
done.

Dropping database table nmea_gl_gsv (and any dependent objects) if it exists.
Dropping database table nmea_gn_gga (and any dependent objects) if it exists.
Dropping database table nmea_gn_gll (and any dependent objects) if it exists.
Dropping database table nmea_gn_gsa (and any dependent objects) if it exists.
Dropping database table nmea_gn_rmc (and any dependent objects) if it exists.
Dropping database table nmea_gn_vtg (and any dependent objects) if it exists.
Dropping database table nmea_gp_gsv (and any dependent objects) if it exists.

Writing data to database... data from logfile 'test_data/test_data_0_all.nmea' written to:
  'nmea_gn_rmc' table in 'nmea_data' database
  'nmea_gn_vtg' table in 'nmea_data' database
  'nmea_gn_gga' table in 'nmea_data' database
  'nmea_gn_gsa' table in 'nmea_data' database
  'nmea_gp_gsv' table in 'nmea_data' database
  'nmea_gl_gsv' table in 'nmea_data' database
  'nmea_gn_gll' table in 'nmea_data' database
done.

All done. Exiting.
```

### Example 3
Convert sentences, all of the same `talker`+`sentence_type`, to database:
```
$ python nmea_data_convert.py test_data/test_data_0_GNVTG.nmea db --spc 1

Reading in data... done.

Processing data... done.

Writing data to database... data from logfile 'test_data/test_data_0_GNVTG.nmea' written to:
  'nmea_gn_vtg' table in 'nmea_data' database
done.

All done. Exiting.

```

### Example 4
Convert GSV sentences, all of the same `talker`, to database, where there may sometimes be multiple messages from the same cycle. In this case, cycles must start with the sentence having the `msg_num` field equal to `1` (see `test_data/test_data_0_GPGSV.nmea`:
```
$ python nmea_data_convert.py test_data/test_data_0_GPGSV.nmea db
[output excluded for brevity]
```

### Example 5
Convert GSA sentences, all of the same `talker`, to database, where each sentence is part of a cycle containing two GSA sentences. Cycles may contain a GSA sentence for each constellation (see `test_data/test_data_0_GNGSA.nmea`:
```
$ python nmea_data_convert.py test_data/test_data_0_GNGSA.nmea db --spc 2
[output excluded for brevity]
```


## Helpful References
* https://github.com/Knio/pynmea2/blob/master/README.md
* https://www.u-blox.com/sites/default/files/products/documents/u-blox8-M8_ReceiverDescrProtSpec_%28UBX-13003221%29.pdf (section 31 'NMEA Protocol')
* https://www.sparkfun.com/datasheets/GPS/NMEA%20Reference%20Manual1.pdf
* https://www.trimble.com/OEM_ReceiverHelp/V4.44/en/NMEA-0183messages_MessageOverview.html
* Talker Identifiers : https://www.nmea.org/Assets/20190303%20nmea%200183%20talker%20identifier%20mnemonics.pdf
* Glossary : https://www.unavco.org/help/glossary/glossary.html
* https://gpsd.gitlab.io/gpsd/NMEA.html#_nmea_standard_sentences

## Support
If you find this tool useful, please consider supporting development of this tool and other tools like it. You can do so using the `Sponsor` button at the top of the [GitHub page](https://github.com/Petrichor-Labs/nmea_data_convert).


## Discussion
For any questions, feedback, or other discussion items, please feel free to post in the [`Discussions` tab on the GitHub page](https://github.com/Petrichor-Labs/nmea_data_convert/discussions).