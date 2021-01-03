This library makes use of [pynmea2](https://github.com/Knio/pynmea2) to parse through input NMEA 0183 data, organize it, and output it to CSV files or to a PostgreSQL database.

## Setup

Your input file should have a format similiar to those under `test_data`. To have your data datetime stamped, it must be in a format like that of `test_data/test_data_all.nmea`, with RMC sentences containing date and time stamps proceed other sentences in the same cycle.

If working with a database, the database access information/credentials must be setup in `db_creds.py`.

The `cycle_start` `talker`+`sentence_type`, e.g. `GNRMC`, passed to `datetime_stamp_sentences()` and `assign_cycle_ids()`, must appear once and only once in each cycle, and it must be at the beginning of each cycle. For sentences to be datetime stamped, `cycle_start` sentences must contain date and time information. The `--backfill_datetimes` flag can be used to back fill datetimes for cycles where that information was not avaiable.


## Usage
```
$ cd nmea_data_convert/
$ pip install -r requirements.txt 
...
$ python nmea_data_convert.py --help
usage: nmea_data_convert.py [-h] [--drop_previous_db_tables]
                            [--backfill_datetimes]
                            filepath {csv,db,both}

positional arguments:
  filepath              file system path to file containing NMEA data
  {csv,db,both}         where to output data: CSV files, database, or both

optional arguments:
  -h, --help            show this help message and exit
  --drop_previous_db_tables, --dropt
                        drop previous DB tables before importing new data;
                        only applies when output_method is 'db' or 'both'
  --backfill_datetimes, --bfdt
                        backfill datetimes where missing by extrapolating from
                        messages with datetime information
```
## Examples
### Example 1
```
$ ls -l *.csv
ls: *.csv: No such file or directory
$ python nmea_data_convert.py test_data/test_data_all.nmea csv

Reading in data... done.

Processing data... done.

Writing data to CSVs... data from logfile 'test_data/test_data_all.nmea' written to:
  test_data_all_GNRMC.csv
  test_data_all_GNVTG.csv
  test_data_all_GNGGA.csv
  test_data_all_GNGSA.csv
  test_data_all_GPGSV.csv
  test_data_all_GLGSV.csv
  test_data_all_GNGLL.csv
done.

All done. Exiting.


$ ls -l *.csv
-rw-r--r--  1 Thomas  staff  14310 Dec 30 18:19 test_data_all_GLGSV.csv
-rw-r--r--  1 Thomas  staff   9502 Dec 30 18:19 test_data_all_GNGGA.csv
-rw-r--r--  1 Thomas  staff   6852 Dec 30 18:19 test_data_all_GNGLL.csv
-rw-r--r--  1 Thomas  staff  18472 Dec 30 18:19 test_data_all_GNGSA.csv
-rw-r--r--  1 Thomas  staff   8672 Dec 30 18:19 test_data_all_GNRMC.csv
-rw-r--r--  1 Thomas  staff   5779 Dec 30 18:19 test_data_all_GNVTG.csv
-rw-r--r--  1 Thomas  staff  40263 Dec 30 18:19 test_data_all_GPGSV.csv
```

### Example 2
```
$ python nmea_data_convert.py test_data/test_data_all.nmea db

Reading in data... done.

Processing data... done.

Writing data to database... data from logfile 'test_data/test_data_all.nmea' written to:
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
```
$ python nmea_data_convert.py test_data/test_data_all.nmea both --bfdt --dropt

Reading in data... done.

Processing data... done.

Writing data to CSVs... data from logfile 'test_data/test_data_all.nmea' written to:
  test_data_all_GNRMC.csv
  test_data_all_GNVTG.csv
  test_data_all_GNGGA.csv
  test_data_all_GNGSA.csv
  test_data_all_GPGSV.csv
  test_data_all_GLGSV.csv
  test_data_all_GNGLL.csv
done.

Dropping database table nmea_gl_gsv (and any dependent objects) if it exists.
Dropping database table nmea_gn_gga (and any dependent objects) if it exists.
Dropping database table nmea_gn_gll (and any dependent objects) if it exists.
Dropping database table nmea_gn_gsa (and any dependent objects) if it exists.
Dropping database table nmea_gn_rmc (and any dependent objects) if it exists.
Dropping database table nmea_gn_vtg (and any dependent objects) if it exists.
Dropping database table nmea_gp_gsv (and any dependent objects) if it exists.

Writing data to database... data from logfile 'test_data/test_data_all.nmea' written to:
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


## References Used in Development
https://github.com/Knio/pynmea2/blob/master/README.md

https://www.trimble.com/OEM_ReceiverHelp/V4.44/en/NMEA-0183messages_MessageOverview.html

https://www.u-blox.com/sites/default/files/products/documents/u-blox8-M8_ReceiverDescrProtSpec_%28UBX-13003221%29.pdf (section 31 'NMEA Protocol')

https://www.sparkfun.com/datasheets/GPS/NMEA%20Reference%20Manual1.pdf

https://www.nmea.org/Assets/20190303%20nmea%200183%20talker%20identifier%20mnemonics.pdf

https://www.unavco.org/help/glossary/glossary.html


## Support
If you find this tool useful, please consider supporting development of this tool and other tools like it. You can do so using the `Sponsor` button at the top of the [GitHub page](https://github.com/Petrichor-Labs/nmea_data_convert).


## Discussion
For any questions, feedback, or other discussion items, please feel free to post in the [`Discussions` tab on the GitHub page](https://github.com/Petrichor-Labs/nmea_data_convert/discussions).