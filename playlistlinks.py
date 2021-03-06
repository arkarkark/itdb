#!/usr/bin/env python3
# Copyright 2007 Alex K (wtwf.com) All rights reserved.

"""Create a bunch of symlinks from a playlist name.

Useful for making CDs/DVDs of multiple playlists using mkisofs -posix-L

mkisofs -posix-L -R -J -o ~/tmp/disk.iso ~/tmp/out/

you can get mkisofs from macports.org - sudo port install cdrtools

Usage: %(PROGRAM)s
  -p playlist_name
  --playlist=name - create links for this playlist

  -l playlist_like
  --like=name - find all playlists matching like pattern and make links

  --folder=name - find all playlists under this folder playlist

  -d destination
  --destination=directory - create links in this directory

  -s number
  --start_number=number - prefix links starting with this number

  -r
  --random - shuffle the files before making the links.

  -w where_clause
  --where=where_clause - use this to select tracks

  -c
  --cp copy files rather than making symlinks

  -u
  --usb copy this to a USB drive (or phone)

  -f format
  --format format use this string to format the filename

  --nonewmusic don't copy or make new music links. only include in m3u if there.

  --sync sync all the playlists on a device (implies --usb)
"""


import atexit
import getopt
import logging
import os
import random
import shutil
import sys
import urllib

import MySQLdb
import MySQLdb.cursors

__pychecker__ = "unusednames=PROGRAM,_a,_b"

COLUMNS = [
    "Track_ID",
    "Name",
    "Artist",
    "Album",
    "Genre",
    "Kind",
    "Size",
    "Total_Time",
    "Disc_Number",
    "Disc_Count",
    "Track_Number",
    "Track_Count",
    "Year",
    "Date_Modified",
    "Date_Added",
    "Skip_Date",
    "Skip_Count",
    "Bit_Rate",
    "Sample_Rate",
    "Play_Count",
    "Play_Date_UTC",
    "Rating",
    "Artwork_Count",
    "Season",
    "Persistent_ID",
    "Track_Type",
    "File_Type",
    "File_Creator",
    "Location",
    "File_Folder_Count",
    "Library_Folder_Count",
]


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


class PlaylistLinks:
    def __init__(self, dbconfig):
        """    """
        self.conn = MySQLdb.connect(
            read_default_file=dbconfig, cursorclass=MySQLdb.cursors.DictCursor
        )
        atexit.register(self.close)
        self.cursor = self.conn.cursor()
        self.random_ordering = False
        self.number = 0
        self.destination_directory = os.path.expanduser("~/tmp/out")
        self.format = ""
        self.copy = False
        self.m3u = False
        self.nonewmusic = False

    def close(self):
        if self.conn:
            logging.info("Closing db")
            self.conn.close()
            self.conn = None

    def get_playlist_id(self, playlist):
        sql = "SELECT Playlist_ID AS id from playlists WHERE name = %s"
        self.cursor.execute(sql, (playlist,))
        if self.cursor.rowcount == 1:
            result = self.cursor.fetchone()
            return int(result["id"])
        return None

    def from_playlist_like(self, like):
        # find all the playlists like this. then FromPlaylist them...
        sql = "SELECT Name, Playlist_ID AS id FROM Playlists WHERE Name LIKE %s"
        self.cursor.execute(sql, (like,))
        for playlist in self.cursor.fetchall():
            self.from_playlist_id(playlist["Name"], playlist["id"])

    def from_playlist(self, playlist):
        # Find the playlist id
        playlist_id = self.get_playlist_id(playlist)
        if playlist_id is None:
            logging.fatal("Unable to find playlist: %s", playlist)
        self.from_playlist_id(playlist, playlist_id)

    def from_folder(self, folder):
        sql = "SELECT Playlist_Persistent_ID FROM Playlists WHERE Name = %s"
        self.cursor.execute(sql, (folder,))
        ids = [x["Playlist_Persistent_ID"] for x in self.cursor.fetchall()]
        for playlist_id in ids:
            sql = """SELECT Name AS name, Playlist_ID AS id FROM Playlists
          WHERE Parent_Persistent_ID = %s"""
            self.cursor.execute(sql, (playlist_id,))
            for row in self.cursor.fetchall():
                self.from_playlist_id(row["name"], row["id"])

    def from_playlist_id(self, playlist, playlist_id):
        sel = ", ".join(["tracks.%s as %s" % (x, x) for x in COLUMNS])
        sql = (
            "SELECT " + sel + " FROM tracks, playlist_tracks "
            "WHERE tracks.Track_ID = playlist_tracks.Track_ID "
            "AND playlist_tracks.Playlist_ID = %s;"
        )
        self.cursor.execute(sql, (playlist_id,))
        results = self.cursor.fetchall()
        self.make_links_from_location(
            playlist, "Playlist:%s:%s" % (playlist_id, playlist), results
        )

    def from_where_clause(self, where, name):
        # TODO(ark): make a file with the whereclause in it for sync
        sql = "SELECT " + ",".join(COLUMNS) + " FROM tracks WHERE %s " % where
        self.cursor.execute(sql)
        results = self.cursor.fetchall()

        # TODO(ark): make a name and a description for m3u file
        self.make_links_from_location(name, None, results)

    def make_links_from_location(self, name, description, results):
        if self.random_ordering:
            logging.debug("Randomizing playlist")
            random.shuffle(results)

        if self.format.lower() != "itunes":
            format_str = os.path.join(self.format, "%(number)03d-%(basename)s")
            # make a subdirectory and rename destination_directory
            destination_directory = os.path.join(self.destination_directory, name)
        else:
            format_str = None
            destination_directory = self.destination_directory

        if not os.path.exists(destination_directory):
            os.makedirs(destination_directory)

        logging.info(
            "Playlist: %s (Making links for %d files in %s)",
            name,
            len(results),
            destination_directory,
        )

        m3u_file = None
        for result in results:
            filename = self.get_filename_from_result(result)
            result["number"] = self.number
            result["basename"] = os.path.basename(filename)

            if format_str:
                link = format_str % result
            else:
                link = os.path.sep.join(filename.split(os.path.sep)[-3:])
            link = os.path.join(destination_directory, link)

            self.number += 1
            exists = False
            if os.path.exists(filename):
                directory = os.path.dirname(link)
                if not os.path.exists(directory):
                    os.makedirs(directory)

                if not os.path.exists(link):
                    if not self.nonewmusic:
                        if self.copy:
                            logging.debug("Copying %s from %s", link, filename)
                            shutil.copyfile(filename, link)
                            exists = True
                        else:
                            logging.debug("Linking %s from %s", link, filename)
                            try:
                                os.symlink(filename, link)
                                exists = True
                            except Exception as ex:
                                logging.error(
                                    "\n\n\nsymlink error: %r %r",
                                    os.path.exists(link),
                                    ex,
                                )
                    else:
                        logging.debug("Skipping (nonewmusic) %s %s", link, filename)
                else:
                    logging.debug("Exists  %s", os.path.basename(link))
                    exists = True
            else:
                if not self.nonewmusic:
                    logging.error("Source file does not exist: %s", filename)

            if m3u_file or (self.m3u and name and description and exists):
                if not m3u_file:
                    m3u_filename = os.path.join(destination_directory, name + ".m3u")
                    m3u_file = open(m3u_filename, "w")
                    m3u_file.write("#ITDBDESC:%s\n" % description)
                m3u_file.write(
                    "#ITDBFILE:%s:%s\n" % (result["Track_ID"], result["Location"])
                )
                m3u_file.write("%s\n" % link[len(destination_directory) + 1 :])

        if m3u_file:
            m3u_file.close()
        logging.debug("Done Making links for %d files", len(results))

    def get_filename_from_result(self, result):
        """turns a location into a real file location

    Locations look like this:
    file://localhost/Volumes/Data/Music/Sleeper/Smart/03%20Delicious.mp3

    Filenames look like this:
    /Volumes/Data/Music/Sleeper/Smart/03 Delicious.mp3
    """
        # strip of localhost part
        localhost = "file://localhost"
        location = result["Location"]
        if location.startswith(localhost):
            location = location[len(localhost) :]
        # url unescape
        return urllib.parse.unquote(location)

    def sync(self):
        """Make sure a directory is up to date."""
        for filename in os.listdir(self.destination_directory):
            playlist = os.path.basename(filename)
            playlist_id = self.get_playlist_id(playlist)
            if playlist_id is None:
                logging.info("Not Syncing: %s", playlist)
            else:
                self.sync_playlist(playlist, playlist_id)

    def sync_playlist(self, playlist, playlist_id):
        logging.info("Syncing Playlist: %s (%s)", playlist, playlist_id)

        logging.fatal("Syncing Playlists is not yet supported!")
        # get files in directory

        # get files in playlist

        # work out what's missing

        # remove what's extra

        # write new m3u


def find_usb():
    paths = ("/Volumes/WTWFDOTCOM", "/Volumes/NexusOne")
    for path in paths:
        if os.path.exists(path):
            logging.info("Using USB drive: %s", path)
            return path
    return usage("unable to find any USB drives, perhaps use the --destination option")


def main():
    """Parse flags, setup logging and go!"""

    logging.basicConfig()
    log_level = logging.INFO  # this is 20 - they go in steps of 10
    logging.getLogger().setLevel(logging.INFO)
    logging.info("Starting %s", " ".join(sys.argv))

    # parse command line options
    try:
        opts, _ = getopt.getopt(
            sys.argv[1:],
            "cd:f:hl:mn:p:rs:uvw:",
            [
                "copy",
                "destination=",
                "folder=",
                "format=",
                "help",
                "like=",
                "m3u",
                "name=",
                "nonewmusic",
                "playlist=",
                "random",
                "start_number=",
                "sync",
                "usb",
                "verbose",
                "where=",
            ],
        )
    except getopt.error as msg:
        usage(msg=msg)

    # Process options

    dbconfig = os.path.expanduser("~/.itdb.config")
    name = None

    pll = PlaylistLinks(dbconfig)

    for opt, arg in opts:
        if opt in ("-c", "--copy"):
            pll.copy = True
        if opt in ("-d", "--destination"):
            pll.destination_directory = arg
        if opt in ("--folder",):
            pll.from_folder(arg)
        if opt in ("-f", "--format"):
            pll.format = arg
        if opt in ("-h", "--help"):
            usage()
        if opt in ("-l", "--like"):
            pll.from_playlist_like(arg)
        if opt in ("-m", "--m3u"):
            pll.m3u = True
        if opt in ("-n", "--name"):
            name = arg
        if opt in ("--nonewmusic",):
            logging.info("No new music links will be added...")
            pll.nonewmusic = True
        if opt in ("-p", "--playlist"):
            pll.from_playlist(arg)
        if opt in ("-r", "--random"):
            pll.random_ordering = True
        if opt in ("-s", "--start_number"):
            pll.number = int(arg)
        if opt in ("--sync",):
            if pll.destination_directory is None:
                pll.destination_directory = find_usb()
            pll.sync()  # TODO(ark): work in progress
        if opt in ("-u", "--usb"):
            if pll.destination_directory is None:
                pll.destination_directory = find_usb()
            pll.copy = True
            pll.m3u = True
        if opt in ("-v", "--verbose"):
            log_level -= 10
            logging.getLogger().setLevel(logging.INFO)
        if opt in ("-w", "--where"):
            if not name:
                usage(msg="You must provide a name when using where")
            else:
                pll.from_where_clause(arg, name)

    pll.close()
    if os.path.exists(pll.destination_directory):
        depth = 1 if pll.format.lower() != "itunes" else 0
        cmd = """(cd "%s" && du -Lh -d %d .)""" % (pll.destination_directory, depth)
        print("\n Disk Size: %s" % cmd)
        os.system(cmd)
        print(
            (
                """\nmkisofs -f -R -J -m .DS_Store -o ~/tmp/disk.iso "%s" """
                % pll.destination_directory
            )
        )
        print(
            ("rsync -avubL %s /Volumes/some_destination/" % pll.destination_directory)
        )


if __name__ == "__main__":
    main()
