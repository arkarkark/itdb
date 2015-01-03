#!/usr/bin/python
# Created by: Alex K (wtwf.com) Sat Mar  4 09:15:22 2006
# Copyright 2006 all rights reserved

"""Make some useful itunes html pages from the data in the database

It uses Cheetah templates
Cheetah http://www.cheetahtemplate.org/

Can also run as a cgi script to fill in missing pages

Usage: %(PROGRAM)s [options]

Options:
  -i
    generate the index page
  -h/--help
    Print this message and exit

TODO(ark) FIX KNOWN BUGS:
clicking on empty album, artist and genre yields an error
clicking on playlists by stars in playlists is wrong link
clicking sort by artist isn't working
- on ?album=MTV+Unplugged

TODO(ark):
download as m3u playlist
download as xml iTunes playlist
browse all (artists/albums) by choosing letters
redo quality to make it top heavy
have a permission denied file (for index and auth failures)
"""

import sys
import os
import logging
import ConfigParser
import MySQLdb
import datetime
import atexit
import math
import locale
import urllib
import cgi
import cgitb
import getopt

from Cheetah.Template import Template

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


ALLOWED_FILENAME_CHARS = ("ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                          "abcdefghijklmnopqrstuvwxyz"
                          "0123456789-_.")

def getFilename(base):
  if not base or len(base) == 0:
    return "_NONE_"
  return "".join([ALLOWED_FILENAME_CHARS.find(x) != -1 and x or "_" for x in base])


class Grouping:
  def __init__(self, name, type, num_stars=None, extension=None):
    """name is the the name e.g. "Classical"
    type is the type of grouping: playlist, album, artist, genre
    """
    self.name = name
    self.type = type
    self.dispName = name or '<i>empty</i>'
    self.filename = getFilename(name)
    self.stars = [0, 0, 0, 0, 0, 0]
    self.num_stars = num_stars
    self.extension = extension or ".html"

  def addStars(self, stars, count):
    self.stars[int(stars)] += int(count)

  def getQuality(self):
    """The quality of this genre from 0 to 5.
    Quality is the average number of stars (not including zero stars).
    quality is not zero ONLY if more than 20% of songs have been rated"""
    tot = float(sum(self.stars[1:]))
    if tot < 1 or (tot * 5) < sum(self.stars):
      return 0
    else:
      return float(sum([x * self.stars[x] for x in range(1, 6)])) / tot

  def getTotal(self):
    """How manny songs are in this genre"""
    return sum(self.stars)

  def PrintDebug(self):
    logging.debug("type: %s - - name: %s - - stars: %s",
                  self.type, self.name, str(self.num_stars))


class FormatUtil:

  def __init__(self, remapping=None):
    if remapping:
      self.remapping = remapping
    else:
      self.remapping = {}

  def getStars(self, rating):
    """Get the number of stars for a rating"""
    return int(math.floor(rating/ 20))

  def formatTime(self, time):
    """Time seems to be number of milliseconds"""
    ans = str(datetime.timedelta(milliseconds=time))
    ans = ans.lstrip("0:")
    idx = ans.rfind(".")
    if idx > 0:
      ans = ans[0:idx]
    return ans

  def getStarsHTML(self, stars, vertical=False, dir=""):
    """Get some HTML for some stars
    I really should use &#9733; for star and &middot; for the dot
    """
    ans = []
    if not vertical:
      ans.append("<nobr>")
    for x in range(0, 5):
      if stars > x:
        ans.append('<img border=0 src="%sratingstar.gif" alt="*">' % dir)
      else:
        ans.append('<img border=0 src="%sratingdot.gif" alt=".">' % dir)
      if vertical:
        ans.append('<br>')
    if not vertical:
      ans.append("</nobr>")
    return "".join(ans)

  def getUrl(self, url):
    urllen = len(url)
    for key in self.remapping.keys():
      if url[0:min(urllen, len(key))] == key:
        return self.remapping[key] + url[len(key):]
    return url

  def getFilename(self, base):
    return getFilename(base)

  def getLocation(self, base):
    return urllib.unquote_plus(self.getUrl(base))

  def sum(self, list):
    return sum(list)

  def urlencode(self, str):
    return urllib.quote_plus(str)

  def htmlencode(self, str):
    return cgi.escape(str)

  def capwords(self, str):
    return " ".join([x.capitalize() for x in str.split(" ")])

  def getTabName(self, str):
    if str == "overview":
      return "Overview"
    return "Top %ss" % self.capwords(str)


class iTunesDbToHtml:

  def __init__(self, config):
    self.config = config
    self.conn = None
    self.userId = int(config.get("user", "id"))
    self.dir = config.get("html", "dir")
    self.base = config.get("html", "base")
    self.script = self.base + '/' + config.get("html", "script")
    logging.info('dir is : %r', self.dir)

    atexit.register(self.close)
    #  locale.setlocale(locale.LC_ALL, "en_US")
    locale.setlocale(locale.LC_ALL, "en_US.UTF-8")

    remapping = {}
    for option in config.options("remapping"):
      if option[0] == "s":
        doption = "d" + option[1:]
        remapping[config.get("remapping", option)] = config.get("remapping",
                                                                doption)
    self.util = FormatUtil(remapping=remapping)

    self.statsTemplate = self.GetTemplate("stats.tmpl.html")
    self.filesTemplate = self.GetTemplate("filelist.tmpl.html")
    self.filesTemplateM3u = self.GetTemplate("filelist.tmpl.m3u")
    self.headerTemplate = self.GetTemplate("header.tmpl.html")

  def GetTemplate(self, name):
    templatedir = self.config.get("templates", "dir")
    t = Template(file=os.path.join(templatedir, name))
    t.util = self.util
    t.base = self.base
    t.script = self.script
    return t


  def Connect(self):
    logging.info("Connecting to db")
    if self.conn is None:
      self.conn = MySQLdb.connect(host=self.config.get("client", "host"),
                                  db=self.config.get("client", "database"),
                                  user=self.config.get("client", "user"),
                                  passwd=self.config.get("client", "password"))
      self.cursor = self.conn.cursor()
    self.filesTemplate.index = self.getTracksIndex()
    self.filesTemplateM3u.index = self.getTracksIndex()

  def getTracksIndex(self):
    indexl = self.getSqlArr("DESCRIBE tracks")
    index = {}
    for x in range(0, len(indexl)):
      index[indexl[x]] = x
    return index

  def close(self):
    logging.info("Closing db")
    if self.conn is not None:
      self.conn.close()

  def updateStatus(self, out):
    """Print a dot on every fifteenth item"""
    if not out.__mod__(15):
      sys.stdout.write('.')
      sys.stdout.flush()

  def getSqlInt(self, sql):
    self.cursor.execute(sql)
    row = self.cursor.fetchone()
    if row == None:
      return None
    return int(row[0])

  def getSqlArr(self, sql):
    # logging.debug(sql)
    self.cursor.execute(sql)
    rows = self.cursor.fetchall()
    if rows == None:
      return []
    return [row[0] for row in rows]

  def getGenresData(self):
    self.cursor.execute("SELECT "
                        "CASE WHEN ISNULL(Genre) THEN '' ELSE Genre END"
                        " AS DaGenre, "
                        "CASE WHEN ISNULL(Rating) THEN 0 "
                        "ELSE FLOOR(Rating/20) END "
                        " AS Stars, "
                        "COUNT(*) "
                        "FROM tracks "
                        "WHERE User_ID=%d "
                        "GROUP BY DaGenre, Stars" % self.userId)
    genres = {}
    row = self.cursor.fetchone()
    while row:
      if not genres.has_key(row[0]):
        genres[row[0]] = Grouping(row[0], "genre")
      genres[row[0]].addStars(row[1], row[2])
      row = self.cursor.fetchone()
    return genres.values()

  def getThingData(self, thing):
    userId = self.userId

    self.cursor.execute("SELECT %(thing)s, "
                        "CASE WHEN ISNULL(Rating) THEN 0 "
                        "ELSE FLOOR(Rating/20) END as Stars, "
                        "COUNT(*) as count FROM tracks "
                        "WHERE User_ID=%(userId)d "
                        "AND %(thing)s IS NOT NULL "
                        "AND LENGTH(%(thing)s) != 0 "
                        "GROUP BY %(thing)s, Stars " % locals())
    things = {}
    row = self.cursor.fetchone()
    while row:
      if not things.has_key(row[0]):
        things[row[0]] = Grouping(row[0], "genre")
      things[row[0]].addStars(row[1], row[2])
      row = self.cursor.fetchone()

    things = things.values()
    return things

  def getStarsFromDb(self, thing, where):
    logging.debug("Where: %s", where)
    sql = ("SELECT "
           "CASE WHEN ISNULL(Rating) THEN 0 "
           "ELSE FLOOR(Rating/20) END as Stars "
           ", COUNT(*) FROM tracks WHERE User_ID = %d AND %s "
           "GROUP BY Rating ORDER BY Rating" %
           (self.userId, where))
    self.cursor.execute(sql)
    tracks = self.cursor.fetchall()
    for track in tracks:
      thing.addStars(track[0], track[1])

  def writeTrackList(self, title, thing, where=None, tracks=None):
    """You can call this with a list of tracks, or a where clause for the db
    """

    filename = self.GetThingFilename(thing)
    if where:
      logging.debug("Writing: %s for %s", os.path.basename(filename), where)
      sql = ("SELECT * FROM tracks WHERE User_ID = %d AND %s ORDER BY Name" %
             (self.userId, where))
      self.cursor.execute(sql)
      tracks = self.cursor.fetchall()
    elif tracks == None:
      logging.debug("Writing: %s for %d Tracks",
                    os.path.basename(filename), len(tracks))
      raise Exception, "You must provide either a where or tracks argument"

    f = open(os.path.join(self.dir, filename), "w")
    self.filesTemplate.tracks = tracks
    self.filesTemplate.title = title
    self.filesTemplate.thing = thing

    f.write(str(self.filesTemplate))
    f.close()
    return filename

  def RMRF(self, dir):
    assert(dir != "/")
    assert(dir.startswith(self.config.get("html", "dir")))
    logging.debug("rm -rf %s", dir)
    for root, dirs, files in os.walk(dir, topdown=False):
      for name in files:
        os.remove(os.path.join(root, name))
      for name in dirs:
        os.rmdir(os.path.join(root, name))

  def ClearCache(self):
    base = self.config.get("html", "dir")
    for dir in ["album", "artist", "playlist", "genre"]:
      self.RMRF(os.path.join(base, dir))

  def WriteStats(self):
    logging.info("Writing Stats")
    self.Connect()
    # get the number of tracks, albums, artists
    totals = {}
    totals["track"] = self.getSqlInt("SELECT COUNT(*) FROM tracks "
                                     "WHERE User_ID=%d" % self.userId)
    totals["album"] = self.getSqlInt("SELECT COUNT(DISTINCT(Album)) "
                                     "FROM tracks "
                                     "WHERE User_ID=%d" % self.userId)
    totals["artist"] = self.getSqlInt("SELECT COUNT(DISTINCT(Artist)) "
                                      "FROM tracks "
                                      "WHERE User_ID=%d" % self.userId)

    ratings = self.getSqlArr("SELECT COUNT(*) AS Count, "
                             "CASE WHEN ISNULL(Rating) THEN 0 "
                             "ELSE FLOOR(Rating/20) END as Stars "
                             "FROM tracks "
                             "WHERE User_ID=%d "
                             "GROUP BY Stars"
                             % self.userId)
    ratingspercent = []
    for x in range(0, 6):
      ratingspercent.append("%d%%" % ((ratings[x] * 100) / totals["track"]))

    self.genres = self.getGenresData()
    self.genres.sort()

    self.artists = self.getThingData("Artist")
    self.albums = self.getThingData("Album")
    # playlists are different since they're built from db tables
    self.playlists = self.getPlaylists()

    # now make ratings track counts be nicely formatted strings
    ratings = [locale.format("%d", x, True) for x in ratings]
    for (key, val) in totals.items():
      totals[key] = locale.format("%d", val, True)

    self.statsTemplate.totals = totals
    # since we can't seem to have an array of tuples for cheetah I
    # have to have an array and a dictionary
    self.statsTemplate.types = ["overview",
                                "genre", "artist", "playlist", "album"]
    self.statsTemplate.typesdict = {"genre": self.genres,
                                    "artist": self.shrink(self.artists),
                                    "album": self.shrink(self.albums),
                                    "playlist": self.shrink(self.playlists)
                                    }
    self.statsTemplate.ratings = ratings
    self.statsTemplate.ratingspercent = ratingspercent

    for type in self.statsTemplate.types:
      self.statsTemplate.type = type
      dir = os.path.join(self.dir, "stat")
      if not os.path.exists(dir):
        os.mkdir(dir)
      f = open(os.path.join(dir, "%s.html" % type), "w")
      f.write(str(self.statsTemplate))
      f.close()

  def shrink(self, arr):
    """We want all lists (album, playlistsm & artists) to be the same
    length as the Genres list, so we chop it down to twice the size of
    the genres array and then find the highest quality entries and
    then shrink that down to the length of the genres array."""
    # trim down albums
    # sort by number of tracks (highest first)
    arr.sort(lambda x, y: cmp(sum(y.stars), sum(x.stars)))
    # strip if down to length of genres
    arr = arr[0:min(len(arr), len(self.genres) * 2)]
    # order by quality
    arr.sort(lambda x, y: cmp(y.getQuality(), x.getQuality()))
    arr = arr[0:min(len(arr), len(self.genres))]
    return arr

  def getPlaylists(self):
    playlists = []
    rows = []
    self.cursor.execute("SELECT Name, Playlist_ID FROM playlists "
                        "WHERE User_ID = %d" % self.userId)
    row = self.cursor.fetchone()
    while row:
      rows.append((str(row[0]), int(row[1])))
      row = self.cursor.fetchone()

    for (name, plid) in rows:
      playlist = Grouping(name, "playlist")
      playlists.append(self.getPlaylistStats(playlist, plid))

    return playlists


  def getPlaylistStats(self, thing, playlistId):
    """This gets all the tracks and the stats about the tracks from one query"""
    sql = ("SELECT "
           "CASE WHEN ISNULL(Rating) THEN 0 "
           "ELSE FLOOR(Rating/20) END as Stars "
           ", SUM(Count) FROM playlist_stats WHERE "
           "User_ID = %d AND Playlist_ID = %d "
           "GROUP BY Stars" %
           (self.userId, playlistId))
    self.cursor.execute(sql)
    stats = self.cursor.fetchall()
    for stat in stats:
      thing.addStars(stat[0], stat[1])

    return thing

  def writePlaylist(self, thing):
    self.Connect()
    # find the ID for this playlist
    playlist_id = self.getSqlInt("SELECT Playlist_ID FROM playlists WHERE "
                                 "User_ID = %d AND Name = '%s' " %
                                 (self.userId,
                                  MySQLdb.escape_string(thing.name)))
    return self.getPlaylist(thing, playlist_id)


  def getPlaylist(self, thing, playlist_id):
    """This gets all the tracks and the stats about the tracks from one query"""
    logging.debug("Writing playlist: %s (ID:%d)", thing.name, playlist_id)
    sql = ("SELECT * FROM tracks "
           "INNER JOIN playlist_tracks "
           "ON tracks.Track_ID = playlist_tracks.Track_ID "
           "AND tracks.User_ID = playlist_tracks.User_ID "
           "WHERE playlist_tracks.Playlist_ID = '%d' "
           "AND tracks.User_ID = %d" %
           (playlist_id, self.userId))
    if thing.num_stars is not None:
      sql += " AND FLOOR(Rating/20) = %d" % thing.num_stars
    self.cursor.execute(sql)
    arr = self.cursor.fetchall()

    self.getPlaylistStats(thing, playlist_id)

    # write out the tracklist
    htmlname = cgi.escape(thing.name)
    filename = self.writeTrackList("Playlists: %s" % htmlname,
                                   thing, tracks=arr)

    return filename



  def WritePlaylistsAsM3u(self):
    self.filesTemplate = self.filesTemplateM3u
    playlists = self.getPlaylists()
    for playlist in playlists:
      print playlist.name
      playlist.extension = '.m3u'
      print self.writePlaylist(playlist)

  def writeThing(self, thing):
    logging.info("Writing %s %s" % (thing.type, thing.name))
    self.Connect()
    # make sure genres directort exists
    count = 0
    column = thing.type # e.g. genre
    sqlname = MySQLdb.escape_string(thing.name)
    htmlname = cgi.escape(thing.name)
    where = "%(column)s='%(sqlname)s'" % locals()
    self.getStarsFromDb(thing, where)
    if thing.num_stars is not None:
      where += " AND FLOOR(Rating/20) = %d" % thing.num_stars
    filename = self.writeTrackList("%(column)s: %(htmlname)s" % locals(),
                        thing, where=where)
    return filename

  def GetThingFilename(self, thing):
    tdir = os.path.join(self.dir, thing.type.lower())
    if not os.path.exists(tdir):
      logging.info("Making directory: %s", tdir)
      os.mkdir(tdir)
    if thing.num_stars is None:
      return os.path.join(tdir, thing.filename + thing.extension)
    else:
      return os.path.join(tdir, thing.filename + ("-%d" % thing.num_stars) +
                          thing.extension)

  def SendFile(self, filename):
    # send the contents of a file
    # includes the header too
    includehead = False
    for line in file(filename).xreadlines():
      if not includehead and line.startswith("<INCLUDEHEAD>"):
        includehead = True
        if 'REMOTE_USER' in os.environ:
          self.headerTemplate.user = os.environ['REMOTE_USER']
        else:
          self.headerTemplate.user = 'arkyark'
        x = str(self.headerTemplate)
        print x
      else:
        print line


def CgiMain(it):
  """Run as a cgi program
  """
  if config.has_option("html", "exceptions") and config.getboolean("html", "exceptions"):
    cgitb.enable()

  print "Content-type: text/html"
  print ""

  if os.path.exists(os.path.join(it.dir, ".loading")):
    it.SendFile(os.path.join(it.dir, "html", "maintenance.html"))
    return

  form = cgi.FieldStorage()

  stars = None
  if "stars" in form:
    stars = int(form["stars"].value)

  type = None
  name = None
  for x in ["genre", "playlist", "album", "artist", "edit", "stat"]:
    if x in form:
      type = x
      name = MySQLdb.escape_string(form[x].value)
      break

  if type in ['genre', 'artist', 'album']:
    thing = Grouping(name, type, stars)
    thing.PrintDebug()
    filename = it.GetThingFilename(thing)
    if not config.getboolean("html", "cache") or not os.path.exists(filename):
      filename = it.writeThing(thing)
    it.SendFile(filename)
  elif type in ["playlist"]:
    thing = Grouping(name, type, stars)
    thing.PrintDebug()
    filename = it.GetThingFilename(thing)
    if not os.path.exists(filename):
      filename = it.writePlaylist(thing)
    it.SendFile(filename)
  elif type in ["settings"]:
    print "I'm so lame, this isn't supported yet"
  elif type in ["stat", None]:
    # the default action (type in ["stat"]):
    type = "stat"
    name = name or "overview"
    thing = Grouping(name, type)
    thing.PrintDebug()
    filename = it.GetThingFilename(thing)
    it.SendFile(filename)
  else:
    print "Unmatched action"

if __name__ == '__main__':
  began = str(datetime.datetime.today())
  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  logging.debug("Starting %s @ %s", " ".join(sys.argv), began)

  try:
    opts, args = getopt.getopt(sys.argv[1:], 'hi',
                               ['help'])
  except getopt.error, msg:
    usage(1, msg)

  if args:
    usage(1)

  config = ConfigParser.ConfigParser()
  config.read(['itdb.config',
               '/export/arkstuff/ark/.itdb.config',
               os.path.expanduser('~/.itdb.config')])

  # if we need to add things to config
  # perhaps based on command line arguments here is where we do it
  # TODO(ark) I think we need a generic --set option
  # config.add_section("webserver")
  # config.set("webserver", "start", "false")

  it = iTunesDbToHtml(config)

  runascgi = True
  for opt, arg in opts:
    if opt in ('-h', '--help'):
      usage(0)
    if opt in ('-i'):
      logging.info("Generating the index page")
      it.ClearCache()
      it.WriteStats()
      runascgi = False
    logging.debug("Started @ %s", began)
    logging.debug("Done    @ %s", str(datetime.datetime.today()))

  if runascgi:
    CgiMain(it)
