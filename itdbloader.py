#!/usr/bin/env python3
# Copyright 2007 Alex K (wtwf.com) All rights reserved.

"""
Loads an iTunes Library XML file into a Mysql database

Usage: %(PROGRAM)s [options]

Options:
  -m
    show the maximum size for each column
  -n
    do not clear the database and the auto generated cache files
  -f
    force the loading even if the .xml file is older than the stat file
  -h/--help
    Print this message and exit
"""

import atexit
import configparser
import datetime
import getopt
import logging
import os
import stat
import sys
import tempfile

from xml.sax._exceptions import SAXParseException

import MySQLdb

import iTunes
import itdb2html

# pylint: disable=missing-docstring


def usage(code=False, msg=""):
    """Show a usage message."""
    file = sys.stderr if code else sys.stdout
    PROGRAM = os.path.basename(  # pylint: disable=invalid-name,possibly-unused-variable
        sys.argv[0]
    )
    print(__doc__ % locals(), file=file)
    if msg:
        print(msg, file=file)
    sys.exit(code)


class iTunesLoader:
    def __init__(self, config):
        self.filename = config.get("iTunes", "xmlfile")
        if (
            config.has_option("iTunes", "clean")
            and config.get("iTunes", "clean").lower()[0] == "y"
        ):
            self.tmp = tempfile.mktemp()
            logging.info("Sanitizing xml into: %s", self.tmp)
            cmd = "tr -cd '\11\12\40-\176' <'%s' >'%s'" % (self.filename, self.tmp)
            logging.info(cmd)
            os.system(cmd)
            self.filename = self.tmp
            # atexit.register(self.cleanup)

        logging.info("loading %s", self.filename)
        self.lib = iTunes.Library(self.filename)
        self.lib.load()
        logging.info("Connecting to db")
        self.conn = MySQLdb.connect(
            host=config.get("client", "host"),
            db=config.get("client", "database"),
            user=config.get("client", "user"),
            passwd=config.get("client", "password"),
        )
        self.conn.autocommit(True)
        atexit.register(self.close)
        self.cursor = self.conn.cursor()
        self.user_id = int(config.get("user", "id"))
        self.max = {}
        # dictionary of column names we're missing (and their max values)
        self.missing = {}
        # column names we don't care if they're missing
        self.ok_to_be_missing = []

    def cleanup(self):
        if hasattr(self, "tmp") and self.tmp and os.path.exists(self.tmp):
            logging.info("Cleaning up: %s", self.tmp)
            os.unlink(self.tmp)

    def close(self):
        logging.info("Closing db")
        self.conn.close()

    def load_tracks(self):
        not_found = True
        num = 0

        # find columns in the tracks table
        self.cursor.execute("DESCRIBE tracks")
        rows = self.cursor.fetchall()
        colums_we_care_about = [row[0] for row in rows]

        logging.debug(
            "We care about these columns: %s", ", ".join(colums_we_care_about)
        )

        logging.info("Loading tracks data")
        not_found = True
        while not_found:
            try:
                info = self.lib.getTrack()
            except EOFError:
                not_found = False
                break

            if not info:
                break

            num += 1
            self.update_status(num, ".", every=20)
            # now load it into the DB

            # we don't load everything, only things we have columns for
            keys = list(info.keys())

            # we'll build a list of coulmns we care about in this list
            newkeys = []
            # find the max lengths
            for key in keys:
                if key not in self.max or len(str(info[key])) > len(self.max[key]):
                    self.max[key] = str(info[key])

                if key.replace(" ", "_") in colums_we_care_about:
                    newkeys.append(key)
                else:
                    if key not in self.missing or len(str(info[key])) > len(
                        self.missing[key]
                    ):
                        self.missing[key] = str(info[key])
            keys = newkeys

            sql = "REPLACE INTO tracks (User_ID, %%s) VALUES (%d, %%s)" % self.user_id
            sql = sql % (
                ", ".join([x.replace(" ", "_") for x in keys]),
                ", ".join(["%%(%s)s" % x for x in keys]),
            )
            try:
                self.cursor.execute(sql, info)
            except Exception as ex:
                logging.error("\nTracks FAIL:%r\nSQL:%s\nINFO:%r\n", ex, sql, info)
                # and keep going...
        print("")

    def load_playlists(self):
        # now for the PlayLists!
        num = 0
        not_found = True
        logging.info("Building Playlists")
        max_name = ""
        while not_found:
            try:
                info = self.lib.getPlaylist()
                if not info:
                    raise EOFError
            except EOFError:
                not_found = False
                break
            except SAXParseException:
                not_found = False
                break

            num += 1
            self.update_status(num, "*", every=1)
            if info:
                # add this playlist

                new_info = {
                    "User ID": self.user_id,
                    "Playlist ID": -1,
                    "Name": "",
                    "Playlist Persistent ID": "",
                    "Parent Persistent ID": "",
                }
                for key in list(new_info.keys()):
                    if key in info:
                        new_info[key] = info[key]

                columns = ", ".join(
                    [x.replace(" ", "_") for x in list(new_info.keys())]
                )
                values = ", ".join(["%%(%s)s" % x for x in list(new_info.keys())])
                sql = "REPLACE INTO playlists (%s) VALUES (%s)" % (columns, values)

                try:
                    self.cursor.execute(sql, new_info)
                except Exception as ex:
                    logging.error(
                        "\nPlaylists FAIL:%r\nSQL:%s\nINFO:%r\n", ex, sql, new_info
                    )

                if len(info["Name"]) > len(max_name):
                    max_name = info["Name"]

                if "Playlist Items" in info:
                    # now add all the songs
                    playlist_id = int(info["Playlist ID"])
                    sql = (
                        "REPLACE INTO playlist_tracks "
                        "(User_ID, Playlist_ID, Track_ID) "
                        "VALUES (%d, %d, %%(Track ID)s)" % (self.user_id, playlist_id)
                    )
                    self.cursor.executemany(sql, info["Playlist Items"])
                    self.load_playlist_stats(playlist_id)
        print(("\nMax name is %d : %s" % (len(max_name), max_name)))

    def load_all_playlist_stats(self):
        rows = []
        self.cursor.execute(
            "SELECT Name, Playlist_ID FROM playlists "
            "WHERE User_ID = %d" % self.user_id
        )
        row = self.cursor.fetchone()
        while row:
            rows.append((str(row[0]), int(row[1])))
            row = self.cursor.fetchone()

        for (name, plid) in rows:
            logging.debug("Stats for: %s", name)
            self.load_playlist_stats(plid)

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

    def update_status(self, out, character=".", every=20):
        """Print a dot on every fiftieth item"""
        if not out.__mod__(every):
            if not out.__mod__(every * 50):
                sys.stdout.write("% 6d\n" % out)
            else:
                sys.stdout.write(character)
            sys.stdout.flush()

    def show_max_lengths(self):
        for key in list(self.max.keys()):
            print(("%20s:%3d:%s" % (key, len(self.max[key]), self.max[key])))
        if self.missing:
            missing_keys = [
                key
                for key in list(self.missing.keys())
                if key not in self.ok_to_be_missing
            ]
            if missing_keys:
                print("\n\n\nThe following table keys are missing:")
                print("Perhaps you should update your itdb.sql?")
                for key in missing_keys:
                    print(
                        (
                            "%20s:%3d:%s"
                            % (key, len(self.missing[key]), self.missing[key])
                        )
                    )

    def clear_database(self):
        self.cursor.execute("DELETE FROM playlist_stats")
        self.cursor.execute("DELETE FROM playlist_tracks")
        self.cursor.execute("DELETE FROM playlists")
        self.cursor.execute("DELETE FROM tracks")


def touch(filename):
    if os.path.exists(filename):
        os.remove(filename)
    file = open(filename, "w")
    file.close()


def main():
    began = str(datetime.datetime.today())
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    try:
        opts, args = getopt.getopt(sys.argv[1:], "cmhfn", ["help"])
    except getopt.error as msg:
        usage(1, msg)

    if args:
        usage(1)

    config = configparser.ConfigParser()
    config.add_section("loader")
    config.set("loader", "showmax", "no")
    config.set("loader", "force", "no")
    config.set("loader", "clear", "yes")
    config.set("loader", "stats", "yes")
    config.read(["itdb.config", os.path.expanduser("~/.itdb.config")])

    for opt, _ in opts:
        if opt in ("-h", "--help"):
            usage(0)
        if opt in ("-m",):
            config.set("loader", "showmax", "true")
        if opt in ("-n",):
            config.set("loader", "clear", "false")
            config.set("loader", "stats", "false")
        if opt in ("-f",):
            config.set("loader", "force", "true")

    xmlfile = config.get("iTunes", "xmlfile")
    directory = config.get("html", "dir")
    loading = os.path.join(directory, ".loading")
    loaded = os.path.join(directory, ".loaded")

    if not os.path.exists(xmlfile):
        usage(9, "ERROR: iTunes xmlfile %r does not exist" % xmlfile)

    # check to see if we really even need to run
    if not (
        config.getboolean("loader", "force")
        or not os.path.exists(loaded)
        or os.stat(loaded)[stat.ST_MTIME] < os.stat(xmlfile)[stat.ST_MTIME]
    ):
        sys.exit()

    logging.debug("Starting %s @ %s", " ".join(sys.argv), began)
    touch(loading)
    itl = iTunesLoader(config)

    if itl:
        if config.getboolean("loader", "clear"):
            logging.info("Clearing database")
            itl.clear_database()

        itl.load_tracks()
        itl.load_playlists()
        if config.getboolean("loader", "showmax"):
            itl.show_max_lengths()

    if config.getboolean("loader", "stats"):
        to_html = itdb2html.iTunesDbToHtml(config)
        to_html.ClearCache()
        to_html.WriteStats()

    # touch the .loaded file
    os.remove(loading)
    touch(loaded)

    logging.debug("Started @ %s", began)
    logging.debug("Done    @ %s", str(datetime.datetime.today()))


if __name__ == "__main__":
    main()
