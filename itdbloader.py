#!/usr/bin/env python3
# Copyright 2019 Alex K (wtwf.com)
# PYTHON_ARGCOMPLETE_OK

"""Load itunes xml into mysql."""

__author__ = "wtwf.com (Alex K)"

import argparse
import atexit
import collections
import configparser
import csv
import datetime
import logging
import os
import plistlib
import stat
import sys

import argcomplete
import humanize
import tqdm
import MySQLdb

import itdb2html


class LogRuntime:
    RUNTIMES = collections.defaultdict(list)

    def __init__(self, name=None, args=None, kwargs=None):
        self.args = args or []
        self.kwargs = kwargs or []
        self.name = name

    def __call__(self, func):
        def wrapped_f(*args, **kwargs):
            start = datetime.datetime.now()
            reply = func(*args, **kwargs)
            delta = start - datetime.datetime.now()
            description = self.name or func.__name__
            description += "("
            description += ", ".join(
                [args[x] for x in self.args] + [f"{x}={kwargs[x]}" for x in self.kwargs]
            )
            description += ")"
            LogRuntime.RUNTIMES[description].append(delta)
            return reply

        return wrapped_f

    @staticmethod
    def show_runtimes():
        print("\nRuntimes:\n")
        for desc, deltas in LogRuntime.RUNTIMES.items():
            duration = ", ".join([humanize.naturaldelta(delta) for delta in deltas])
            print(f"{desc}: {duration}")


atexit.register(LogRuntime.show_runtimes)


def get_config():
    config = configparser.ConfigParser()
    config.add_section("loader")
    config.set("loader", "showmax", "yes")
    config.set("loader", "force", "no")
    config.set("loader", "clear", "yes")
    config.set("loader", "stats", "yes")
    config.read(["itdb.config", os.path.expanduser("~/.itdb.config")])

    return config


def load_itdb(config):
    xmlfile = config.get("iTunes", "xmlfile")
    directory = config.get("html", "dir")
    loading = os.path.join(directory, ".loading")
    loaded = os.path.join(directory, ".loaded")

    if not os.path.exists(xmlfile):
        logging.fatal("ERROR: iTunes xmlfile %r does not exist", xmlfile)

    # check to see if we really even need to run
    if not (
        config.getboolean("loader", "force")
        or not os.path.exists(loaded)
        or os.stat(loaded)[stat.ST_MTIME] < os.stat(xmlfile)[stat.ST_MTIME]
    ):
        sys.exit()

    touch(loading)

    itunes = load_xml(xmlfile)
    DbLoader(config, itunes)

    if config.getboolean("loader", "stats"):
        write_stats(config)

    # touch the .loaded file
    os.remove(loading)
    touch(loaded)


@LogRuntime()
def write_stats(config):
    logging.info("Writing Stats with itdb2html")
    to_html = itdb2html.iTunesDbToHtml(config)
    to_html.ClearCache()
    to_html.WriteStats()


class DbLoader:
    def __init__(self, config, itunes):
        self.itunes = itunes
        self.conn = db_connect(config)
        self.conn.autocommit(True)
        atexit.register(self.close)
        self.cursor = self.conn.cursor()
        self.user_id = int(config.get("user", "id"))
        self.max = {}
        # dictionary of column names we're missing (and their max values)
        self.missing = {}

        if config.getboolean("loader", "clear"):
            logging.info("Clearing database")
            self.clear_database()

        self.load_tracks()
        self.load_playlists()
        if config.getboolean("loader", "showmax"):
            self.show_max_lengths()

    def close(self):
        logging.info("DbLoader: Closing db")
        self.conn.close()

    @LogRuntime()
    def clear_database(self):
        self.cursor.execute("DELETE FROM playlist_stats")
        self.cursor.execute("DELETE FROM playlist_tracks")
        self.cursor.execute("DELETE FROM playlists")
        self.cursor.execute("DELETE FROM tracks")

    @LogRuntime()
    def load_tracks(self):
        tracks = self.itunes["Tracks"]

        columns_we_care_about = self.get_track_columns()

        tracks_csv_filename = "/tmp/itdb_tracks.csv"
        logging.info("Making tracks csv")
        with open(tracks_csv_filename, "w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            for track in tqdm.tqdm(tracks.values()):
                track["User_ID"] = self.user_id

                # we don't load everything, only things we have columns for
                keys = list(track.keys())

                def convert(val):
                    return isinstance(val, bool) and (val and "1" or "0") or str(val)

                row = [
                    convert(track.get(x.replace("_", " ")))
                    for x in columns_we_care_about
                ]
                writer.writerow(row)
                for key in keys:
                    if key not in self.max or len(str(track[key])) > len(self.max[key]):
                        self.max[key] = str(track[key])

                    if key.replace(" ", "_") not in columns_we_care_about:
                        if key not in self.missing or len(str(track[key])) > len(
                            self.missing[key]
                        ):
                            self.missing[key] = str(track[key])
        self.load_csv("tracks", tracks_csv_filename)
        print("")

    @LogRuntime()
    def load_playlists(self):
        max_name = ""
        playlist_tracks_filename = "/tmp/itdb_playlist_tracks.csv"
        logging.info("Creating playlists and playlist_tracks csv")
        with open(playlist_tracks_filename, "w") as playlist_tracks:

            for playlist in tqdm.tqdm(self.itunes["Playlists"]):

                new_playlist = {
                    "User ID": self.user_id,
                    "Playlist ID": -1,
                    "Name": "",
                    "Playlist Persistent ID": "",
                    "Parent Persistent ID": "",
                }
                for key in playlist.keys():
                    if key in new_playlist:
                        new_playlist[key] = playlist[key]

                sql = "REPLACE INTO playlists (%s) VALUES (%s)" % (
                    ", ".join([x.replace(" ", "_") for x in list(new_playlist.keys())]),
                    ", ".join(["%%(%s)s" % x for x in list(new_playlist.keys())]),
                )
                try:
                    self.cursor.execute(sql, new_playlist)
                except Exception as ex:
                    logging.error(
                        "\nPlaylists FAIL:%r\nSQL:%s\nINFO:%r\n", ex, sql, new_playlist
                    )
                if len(playlist["Name"]) > len(max_name):
                    max_name = playlist["Name"]

                if "Playlist Items" in playlist:
                    # now add all the songs
                    playlist_id = int(playlist["Playlist ID"])
                    prefix = "%d,%d," % (self.user_id, playlist_id)
                    for item in playlist["Playlist Items"]:
                        print(prefix + str(item["Track ID"]), file=playlist_tracks)
        self.load_csv("playlist_tracks", playlist_tracks_filename)
        self.load_all_playlist_stats()
        self.max["Playlist name"] = max_name

    @LogRuntime(args=[2])
    def load_csv(self, table, filename):
        logging.info("Loading csv into: %r", table)
        os.chmod(filename, 0o644)
        sql = (
            """LOAD DATA INFILE '%s' IGNORE INTO TABLE %s FIELDS TERMINATED BY ',' ENCLOSED BY '"'"""
            % (filename, table)
        )
        try:
            self.cursor.execute(sql)
        except Exception as ex:
            logging.error("\nTracks FAIL:%r\nSQL:%s\n", ex, sql)
        # os.unlink(filename)

    def show_max_lengths(self):
        print("Max field lengths...")
        for key, value in sorted(self.max.items()):
            print("%20s:%3d:%s" % (key, len(value), value))
        if self.missing:
            print("\n\nThe following table keys are missing:")
            print("Perhaps you should update your itdb.sql?")
            for key, value in sorted(self.missing.items()):
                print("%20s:%3d:%s" % (key, len(value), value))

    def get_track_columns(self):
        # find columns in the tracks table
        self.cursor.execute("DESCRIBE tracks")
        rows = self.cursor.fetchall()
        columns_we_care_about = [row[0] for row in rows]

        logging.debug(
            "We care about these columns: %s", ", ".join(sorted(columns_we_care_about))
        )
        return columns_we_care_about

    @LogRuntime()
    def load_all_playlist_stats(self):
        logging.info("Loading all playlist_stats")
        self.cursor.execute(
            "SELECT Playlist_ID FROM playlists WHERE User_ID = %d" % self.user_id
        )
        for (plid,) in tqdm.tqdm(self.cursor.fetchall()):
            self.load_playlist_stats(int(plid))

    def load_playlist_stats(self, playlist_id):
        """Fill out a lookup table with data about stats for playlists.
        This is somewhat expensive so we pre fill it out.
        """
        self.cursor.execute(
            "SELECT "
            "CASE WHEN ISNULL(Rating) THEN 0 "
            "ELSE FLOOR(Rating/20) END as Stars "
            ", COUNT(*) "
            "FROM tracks "
            "INNER JOIN playlist_tracks "
            "ON tracks.Track_ID = playlist_tracks.Track_ID "
            "AND tracks.User_ID = playlist_tracks.User_ID "
            "WHERE playlist_tracks.Playlist_ID = '%d' "
            "AND tracks.User_ID = %d "
            "GROUP BY stars" % (playlist_id, self.user_id)
        )
        arr = self.cursor.fetchall()

        for row in arr:
            self.cursor.execute(
                "REPLACE INTO playlist_stats "
                "(User_ID, Playlist_ID, Rating, Count) VALUES "
                "(%d, %d, %d, %d)" % (self.user_id, playlist_id, row[0] * 20, row[1])
            )


def db_connect(config):
    logging.info("Connecting to MySQL")
    return MySQLdb.connect(
        host=config.get("client", "host"),
        db=config.get("client", "database"),
        user=config.get("client", "user"),
        passwd=config.get("client", "password"),
    )


@LogRuntime()
def load_xml(xmlfile):
    logging.info("Loading XML file: %r", xmlfile)
    with open(xmlfile, "rb") as infile:
        return plistlib.load(infile)


def touch(filename):
    if os.path.exists(filename):
        os.remove(filename)
    file = open(filename, "w")
    file.close()


class ShutdownHandler(logging.Handler):
    def emit(self, record):
        logging.shutdown()
        sys.exit(1)


@LogRuntime()
def main():
    """Parse args and do the thing."""
    logging.basicConfig()
    logging.getLogger().addHandler(ShutdownHandler(level=50))

    config = get_config()

    parser = argparse.ArgumentParser(description="LoadiTunes XML into MySQL.")
    parser.add_argument("-p", "--password", help="Password")
    parser.add_argument("-size", "--size", help="Size", type=int)
    parser.add_argument("-f", "--force", help="Log verbosely", action="store_true")
    parser.add_argument("-v", "--verbose", help="Log verbosely", action="store_true")
    parser.add_argument("-d", "--debug", help="Log debug messages", action="store_true")

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.force:
        config.set("loader", "force", "true")

    load_itdb(config)


if __name__ == "__main__":
    main()
