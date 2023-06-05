#!/usr/bin/env python3
# Copyright 2020 Alex K (wtwf.com)
# PYTHON_ARGCOMPLETE_OK

"""Load metadata about itunes media files into extra tables."""

# select Persistent_ID, JSON_EXTRACT(ffprobe, '$.streams[*].codec_type') from ffprobe;
# select t.name from ffprobe as f left join tracks as t on f.Persistent_ID = t.Persistent_id;
#
# select t.name, f.Persistent_ID, MAX(JSON_EXTRACT(stream, "$.height")) as h from ffprobe_streams as f
# left join tracks as t on f.Persistent_ID = t.Persistent_id group by t.name, f.Persistent_ID having h < 720;

__author__ = "wtwf.com (Alex K)"

import argparse
import atexit
import collections
import configparser
import datetime
import html
import json
import logging
import os
import subprocess
import urllib.parse

import argcomplete
import humanize
import tqdm

import MySQLdb


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


def db_connect(config):
    logging.info("Connecting to MySQL")
    return MySQLdb.connect(
        host=config.get("client", "host"),
        db=config.get("client", "database"),
        user=config.get("client", "user"),
        passwd=config.get("client", "password"),
    )


def get_config():
    config = configparser.ConfigParser()
    config.read(["itdb.config", os.path.expanduser("~/.itdb.config")])

    return config


class ShutdownHandler(logging.Handler):
    def emit(self, record):
        logging.shutdown()
        sys.exit(1)


class ItdbMetadata:
    def __init__(self, config):
        self.config = config
        self.conn = db_connect(config)
        self.conn.autocommit(True)
        atexit.register(self.close)
        self.cursor = self.conn.cursor()
        self.ensure_tables()
        self.get()

    def close(self):
        logging.info("DbLoader: Closing db")
        self.conn.close()

    def ensure_tables(self):
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ffprobe (
	        Persistent_ID VARCHAR(30),
                ffprobe JSON,
	        PRIMARY KEY (Persistent_ID)
            );
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ffprobe_streams (
	        Persistent_ID VARCHAR(30),
	        stream_index INTEGER(1),
                stream JSON,
	        PRIMARY KEY (Persistent_ID, stream_index)
            );
            """
        )

    def get_locations(self):
        sql = (
            "SELECT Location, Persistent_ID FROM tracks "
            "WHERE (TV_Show = TRUE OR Movie = TRUE) AND Persistent_ID NOT IN (SELECT Persistent_ID FROM ffprobe)"
        )
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def get(self):
        locations = self.get_locations()
        for location, persistent_id in tqdm.tqdm(locations):
            file_location = html.unescape(urllib.parse.unquote(location))[7:]
            if os.path.exists(file_location):

                # print(file_location)
                cmds = [
                    "ffprobe",
                    "-hide_banner",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    file_location,
                ]
                # print(" ".join(cmds))

                ffprobe = subprocess.check_output(cmds, stderr=subprocess.DEVNULL)
                self.update_metadata(persistent_id, ffprobe)

            else:
                logging.error("Unable to find: %r", location)

    def update_metadata(self, persistent_id, ffprobe):
        sql = "INSERT INTO ffprobe (Persistent_ID, ffprobe) VALUES (%s, %s)"
        # ON DUPLICATE KEY UPDATE
        try:
            self.cursor.execute(
                "DELETE FROM ffprobe where Persistent_ID = %s", [persistent_id]
            )
            self.cursor.execute(
                "DELETE FROM ffprobe_streams where Persistent_ID = %s", [persistent_id]
            )
            self.cursor.execute(sql, [persistent_id, ffprobe])
            streams = json.loads(ffprobe)["streams"]
            for stream in streams:
                self.cursor.execute(
                    "INSERT INTO ffprobe_streams (Persistent_ID, stream_index, stream) "
                    "VALUES (%s, %s, %s)",
                    [persistent_id, stream["index"], json.dumps(stream)],
                )
        except Exception as e:
            logging.error("Failed for: %r %r", persistent_id, e)


@LogRuntime()
def main():
    """Parse args and do the thing."""
    logging.basicConfig()
    logging.getLogger().addHandler(ShutdownHandler(level=50))

    config = get_config()

    parser = argparse.ArgumentParser(description="Program to do the thing.")
    parser.add_argument("-p", "--password", help="Password")
    parser.add_argument("-size", "--size", help="Size", type=int)
    parser.add_argument("-v", "--verbose", help="Log verbosely", action="store_true")
    parser.add_argument("-d", "--debug", help="Log debug messages", action="store_true")

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Log")
    print("hello")
    ItdbMetadata(config)


if __name__ == "__main__":
    main()
