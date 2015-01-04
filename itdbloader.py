#!/usr/bin/python
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

import sys
import os
import logging
import ConfigParser
import MySQLdb
import tempfile
import atexit
import datetime
import getopt
import stat

from xml.sax._exceptions import SAXParseException

import iTunes
import itdb2html

def usage(code, msg=''):
  if code:
    fd = sys.stderr
  else:
    fd = sys.stdout
  PROGRAM = os.path.basename(sys.argv[0])
  print >> fd, __doc__ % locals()
  if msg:
    print >> fd, msg
  sys.exit(code)

class iTunesLoader:

  def __init__(self, config):
    self.filename = config.get("iTunes", "xmlfile")
    if (config.has_option("iTunes", "clean") and
        config.get("iTunes", "clean").lower()[0] == "y"):
      self.tmp = tempfile.mktemp()
      logging.info("Sanitizing xml into: %s", self.tmp)
      cmd = "tr -cd '\11\12\40-\176' <'%s' >'%s'" % (self.filename, self.tmp)
      logging.info(cmd)
      os.system(cmd)
      self.filename = self.tmp
      atexit.register(self.cleanup)

    logging.info("loading %s", self.filename)
    self.lib = iTunes.Library(self.filename)
    self.lib.load()
    logging.info("Connecting to db")
    self.conn = MySQLdb.connect(host=config.get("client", "host"),
                                db=config.get("client", "database"),
                                user=config.get("client", "user"),
                                passwd=config.get("client", "password"))
    self.conn.autocommit(True)
    atexit.register(self.close)
    self.cursor = self.conn.cursor()
    self.userId = int(config.get("user", "id"))
    self.max = {}
    # dictionary of column names we're missing (and their max values)
    self.missing = {}
    # column names we don't care if they're missing
    self.ok_to_be_missing = []

  def cleanup(self):
    if (hasattr(self, "tmp") and
        self.tmp and
        os.path.exists(self.tmp)):
      logging.info("Cleaning up: %s", self.tmp)
      os.unlink(self.tmp)

  def close(self):
    logging.info("Closing db")
    self.conn.close()

  def LoadTracks(self):
    notFound = True
    num = 0

    # find columns in the tracks table
    self.cursor.execute("DESCRIBE tracks")
    rows = self.cursor.fetchall()
    colums_we_care_about = [row[0] for row in rows]

    logging.debug("We care about these columns: %s",
                  ", ".join(colums_we_care_about))

    logging.info("Loading tracks data")
    notFound = True
    while notFound:
      try:
        info = self.lib.getTrack()
      except EOFError:
        notFound = False
        break

      if not info:
        break

      num += 1
      self.updateStatus(num)
      # now load it into the DB

      # we don't load everything, only things we have columns for
      keys = info.keys()

      # we'll build a list of coulmns we care about in this list
      newkeys = []
      # find the max lengths
      for key in keys:
        if key.replace(" ", "_") in colums_we_care_about:
          newkeys.append(key)
          if (not self.max.has_key(key) or
              len(str(info[key])) > len(self.max[key])):
            self.max[key] = str(info[key])
        else:
          if (not self.missing.has_key(key) or
              len(str(info[key])) > len(self.missing[key])):
            self.missing[key] = str(info[key])
      keys = newkeys

      sql = "REPLACE INTO tracks (User_ID, %%s) VALUES (%d, %%s)" % self.userId
      sql = sql % (", ".join([x.replace(" ", "_") for x in keys]),
                   ", ".join(["%%(%s)s" % x for x in keys]))
      try:
        self.cursor.execute(sql, info)
      except Exception as e:
        logging.error("\nTracks FAIL:%r\nSQL:%s\nINFO:%r\n", e, sql, info)
        # and keep going...
    print ""

  def LoadPlaylists(self):
    # now for the PlayLists!
    num = 0
    notFound = True
    logging.info("Building Playlists")
    maxName = ""
    while notFound:
      try:
        info = self.lib.getPlaylist()
      except EOFError:
        notFound = False
        break;
      except SAXParseException:
        notFound = False
        break;

      num += 1
      self.updateStatus(num)
      if info:
        # add this playlist

        new_info = {
          'User ID': self.userId,
          'Playlist ID': -1,
          'Name': u'',
          'Playlist Persistent ID': u'',
          'Parent Persistent ID': u''
        }
        for key in new_info.keys():
          if key in info:
            new_info[key] = info[key]

        columns = ', '.join([x.replace(' ', '_') for x in new_info.keys()])
        values = ', '.join(['%%(%s)s' % x for x in new_info.keys()])
        sql = "REPLACE INTO playlists (%s) VALUES (%s)" % (columns, values)

        try:
          self.cursor.execute(sql, new_info)
        except Exception as e:
          logging.error("\nPlaylists FAIL:%r\nSQL:%s\nINFO:%r\n",
                        e, sql, new_info)

        if len(info["Name"]) > len(maxName):
          maxName = info["Name"]

        if info.has_key("Playlist Items"):
          # now add all the songs
          playlistId = int(info["Playlist ID"])
          sql = ("REPLACE INTO playlist_tracks "
                 "(User_ID, Playlist_ID, Track_ID) "
                 "VALUES (%d, %d, %%(Track ID)s)" %
                 (self.userId, playlistId))
          self.cursor.executemany(sql, info["Playlist Items"])
          self.LoadPlaylistStats(playlistId)
    print "Max name is %d : %s" % (len(maxName), maxName)

  def LoadAllPlaylistStats(self):
    playlists = []
    rows = []
    self.cursor.execute("SELECT Name, Playlist_ID FROM playlists "
                        "WHERE User_ID = %d" % self.userId)
    row = self.cursor.fetchone()
    while row:
      rows.append((str(row[0]), int(row[1])))
      row = self.cursor.fetchone()

    for (name, plid) in rows:
      logging.debug("Stats for: %s", name)
      self.LoadPlaylistStats(plid)


  def LoadPlaylistStats(self, playlistId):
    """Fill out a lookup table with data about stats for playlists.
    This is somewhat expensive so we pre fill it out.
    """
    self.cursor.execute("SELECT "
                        "CASE WHEN ISNULL(Rating) THEN 0 "
                        "ELSE FLOOR(Rating/20) END as Stars "
                        ", COUNT(*) "
                        "FROM tracks "
                        "INNER JOIN playlist_tracks "
                        "ON tracks.Track_ID = playlist_tracks.Track_ID "
                        "AND tracks.User_ID = playlist_tracks.User_ID "
                        "WHERE playlist_tracks.Playlist_ID = '%d' "
                        "AND tracks.User_ID = %d "
                        "GROUP BY stars" %
                        (playlistId, self.userId))
    arr = self.cursor.fetchall()

    for row in arr:
      self.cursor.execute("REPLACE INTO playlist_stats "
                          "(User_ID, Playlist_ID, Rating, Count) VALUES "
                          "(%d, %d, %d, %d)" %
                          (self.userId, playlistId, row[0] * 20, row[1]))

  def updateStatus(self, out):
    """Print a dot on every fifteenth item"""
    if not out.__mod__(15):
      sys.stdout.write('.')
      sys.stdout.flush()

  def ShowMaxLengths(self):
    for key in self.max.keys():
      print "%20s:%3d:%s" % (key, len(self.max[key]), self.max[key])
    if self.missing:
      self.missing = [key for key in self.missing.keys() if key not in self.ok_to_be_missing and key in self.max]
      if self.missing:
        print "The following table keys are missing:"
        print "Perhaps you should update your itdb.sql?"
        for key in self.missing.keys():
          print "%20s:%3d:%s" % (key, len(self.max[key]), self.max[key])


  def ClearDatabase(self):
    self.cursor.execute("DELETE FROM playlist_stats")
    self.cursor.execute("DELETE FROM playlist_tracks")
    self.cursor.execute("DELETE FROM playlists")
    self.cursor.execute("DELETE FROM tracks")

def touch(filename):
  if os.path.exists(filename):
    os.remove(filename)
  f = open(filename, "w")
  f.close()

if __name__ == '__main__':
  began = str(datetime.datetime.today())
  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  try:
    opts, args = getopt.getopt(sys.argv[1:], 'cmhfn',
                               ['help'])
  except getopt.error, msg:
    usage(1, msg)

  if args:
    usage(1)

  config = ConfigParser.ConfigParser()
  config.add_section("loader")
  config.set("loader", "showmax", "no")
  config.set("loader", "force",  "no")
  config.set("loader", "clear",  "yes")
  config.set("loader", "stats",  "yes")
  config.read(['itdb.config', os.path.expanduser('~/.itdb.config')])

  for opt, arg in opts:
    if opt in ('-h', '--help'):
      usage(0)
    if opt in ('-m'):
      config.set("loader", "showmax", "true")
    if opt in ('-n'):
      config.set("loader", "clear",  "false")
      config.set("loader", "stats",  "false")
    if opt in ('-f'):
      config.set("loader", "force",  "true")

  xmlfile = config.get("iTunes", "xmlfile")
  directory = config.get("html", "dir")
  loading = os.path.join(directory, ".loading")
  loaded = os.path.join(directory, ".loaded")

  if not os.path.exists(xmlfile):
    usage(9, 'ERROR: iTunes xmlfile %r does not exist' % xmlfile)

  # check to see if we really even need to run
  if not (config.getboolean("loader", "force") or
          not os.path.exists(loaded) or
          os.stat(loaded)[stat.ST_MTIME] < os.stat(xmlfile)[stat.ST_MTIME]):
    sys.exit()

  logging.debug("Starting %s @ %s", " ".join(sys.argv), began)
  touch(loading)
  itl = iTunesLoader(config)

  if config.getboolean("loader", "clear"):
    logging.info("Clearing database")
    itl.ClearDatabase()

  itl.LoadTracks()
  itl.LoadPlaylists()
  if config.getboolean("loader", "showmax"):
    itl.ShowMaxLengths()

  if config.getboolean("loader", "stats"):
    it = itdb2html.iTunesDbToHtml(config)
    it.ClearCache()
    it.WriteStats()

  # touch the .loaded file
  os.remove(loading)
  touch(loaded)

  logging.debug("Started @ %s", began)
  logging.debug("Done    @ %s", str(datetime.datetime.today()))
