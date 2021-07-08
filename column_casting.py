import sqlalchemy


# Default database datatype for all non-derived data is text
# This file specifies columns to cast and what the python and database datatypes should be is before importing to database

# Conversion intended to go:
#   str -> py_datatype in correct_data_types()
# and then:
#   py_datatype -> db_dataype in dfs_to_db()
# But that first step is currently disabled, thought to be unnecesary, so conversion goes:
#   str -> db_dataype in dfs_to_db()
# DateTime, boolean, and string data values are handled correctly automatically
# Conversion to db_dataype disregards the sentence_type, so if column db_datatypes are different, column names must be uniquw

# Database datatypes reference: https://www.tutorialspoint.com/postgresql/postgresql_data_types.htm


datatype_dict = {}  # Must contain (key, value) pair for all destination datatypes
datatype_dict['Int16']   = sqlalchemy.types.SmallInteger()
datatype_dict['Int32']   = sqlalchemy.types.Integer()
datatype_dict['float32'] = sqlalchemy.types.Float(precision=6)
datatype_dict['text']    = sqlalchemy.types.Text()


# This db_datatypes dictionary is completed in dfs_to_db()
db_datatypes = {}
db_datatypes['cycle_id'] = sqlalchemy.types.Integer()


columns_to_cast = {}

columns_to_cast['GSV', 'Int16'] = ['num_messages', 'msg_num', 'num_sv_in_view',
                                   'sv_prn_num_1',  'elevation_deg_1',  'azimuth_1',  'snr_1',
                                   'sv_prn_num_2',  'elevation_deg_2',  'azimuth_2',  'snr_2',
                                   'sv_prn_num_3',  'elevation_deg_3',  'azimuth_3',  'snr_3',
                                   'sv_prn_num_4',  'elevation_deg_4',  'azimuth_4',  'snr_4',
                                   'sv_prn_num_5',  'elevation_deg_5',  'azimuth_5',  'snr_5',
                                   'sv_prn_num_6',  'elevation_deg_6',  'azimuth_6',  'snr_6',
                                   'sv_prn_num_7',  'elevation_deg_7',  'azimuth_7',  'snr_7',
                                   'sv_prn_num_8',  'elevation_deg_8',  'azimuth_8',  'snr_8',
                                   'sv_prn_num_9',  'elevation_deg_9',  'azimuth_9',  'snr_9',
                                   'sv_prn_num_10', 'elevation_deg_10', 'azimuth_10', 'snr_10',
                                   'sv_prn_num_11', 'elevation_deg_11', 'azimuth_11', 'snr_11',
                                   'sv_prn_num_12', 'elevation_deg_12', 'azimuth_12', 'snr_12',
                                   'sv_prn_num_13', 'elevation_deg_13', 'azimuth_13', 'snr_13',
                                   'sv_prn_num_14', 'elevation_deg_14', 'azimuth_14', 'snr_14',
                                   'sv_prn_num_15', 'elevation_deg_15', 'azimuth_15', 'snr_15',
                                   'sv_prn_num_16', 'elevation_deg_16', 'azimuth_16', 'snr_16',]

columns_to_cast['RMC', 'Int32']   = ['datestamp']
columns_to_cast['RMC', 'float32'] = ['timestamp', 'lat', 'lon', 'spd_over_grnd', 'true_course', 'mag_variation']
columns_to_cast['RMC', 'text']    = ['status', 'lat_dir', 'lon_dir', 'mode', 'mag_var_dir']

columns_to_cast['GGA', 'float32'] = ['timestamp', 'lat', 'lon', 'horizontal_dil', 'altitude', 'geo_sep']
columns_to_cast['GGA', 'Int16']   = ['gps_qual', 'num_sats']
columns_to_cast['GGA', 'text']    = ['lat_dir', 'altitude_units', 'geo_sep_units']
# TODO: For GGA, unsure about 'age_gps_data' and 'ref_station_id'

columns_to_cast['GLL', 'float32'] = ['lat', 'lon']
columns_to_cast['GLL', 'text']    = ['lat_dir', 'lon_dir', 'status', 'faa_mode']

columns_to_cast['VTG', 'float32'] = ['true_track', 'mag_track', 'spd_over_grnd_kts', 'spd_over_grnd_kmph']
columns_to_cast['VTG', 'text']    = ['true_track_sym', 'mag_track_sym', 'spd_over_grnd_kts_sym', 'spd_over_grnd_kmph_sym', 'faa_mode']

columns_to_cast['GSA', 'Int16']   = ['mode_fix_type', 'gp_sv_id01', 'gp_sv_id02', 'gp_sv_id03', 'gp_sv_id04',
                                                      'gp_sv_id05', 'gp_sv_id06', 'gp_sv_id07', 'gp_sv_id08',
                                                      'gp_sv_id09', 'gp_sv_id10', 'gp_sv_id11', 'gp_sv_id12',
                                                      'gl_sv_id01', 'gl_sv_id02', 'gl_sv_id03', 'gl_sv_id04',
                                                      'gl_sv_id05', 'gl_sv_id06', 'gl_sv_id07', 'gl_sv_id08',
                                                      'gl_sv_id09', 'gl_sv_id10', 'gl_sv_id11', 'gl_sv_id12',]
columns_to_cast['GSA', 'float32'] = ['pdop', 'hdop', 'vdop']
columns_to_cast['GSA', 'text']    = ['mode']


