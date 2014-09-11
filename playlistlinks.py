#!/usr/bin/python
# Copyright 2007 Alex K (wtwf.com) All rights reserved.

"""Create a bunch of symlinks from a playlist name.

Useful for making CDs/DVDs of multiple playlists using mkisofs -posix-L

mkisofs -posix-L -R -J -o ~/tmp/disk.iso ~/tmp/out/

you can get mkisofs from macports.org - sudo port install cdrtools

Usage: %(PROGRAM)s
  -p playlist_name
  --playlist=name - create links for this playlist

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

  --sync sync all the playlists on a device (implies --usb)
"""


import MySQLdb
import MySQLdb.cursors
import atexit
import getopt
import logging
import os
import random
import shutil
import sys
import urllib

__pychecker__ = 'unusednames=PROGRAM,_a,_b'

COLUMNS = ['Track_ID', 'Name', 'Artist', 'Album', 'Genre', 'Kind',
           'Size', 'Total_Time',
           'Disc_Number', 'Disc_Count', 'Track_Number', 'Track_Count',
           'Year', 'Date_Modified', 'Date_Added', 'Skip_Date', 'Skip_Count',
           'Bit_Rate', 'Sample_Rate', 'Play_Count', 'Play_Date_UTC', 'Rating',
           'Artwork_Count', 'Season', 'Persistent_ID', 'Track_Type',
           'File_Type', 'File_Creator', 'Location', 'File_Folder_Count',
           'Library_Folder_Count']

def Usage(code=True, msg=''):
  if code:
    fd = sys.stderr
  else:
    fd = sys.stdout
  PROGRAM = os.path.basename(sys.argv[0])
  print >> fd, __doc__ % locals()
  if msg:
    print >> fd, msg
  sys.exit(code)

class PlaylistLinks:

  def __init__(self, dbconfig):
    """    """
    self.conn = MySQLdb.connect(read_default_file=dbconfig,
                                cursorclass=MySQLdb.cursors.DictCursor)
    atexit.register(self.close)
    self.cursor = self.conn.cursor()
    self.random_ordering = False
    self.number = 0

  def close(self):
    if self.conn:
      logging.info('Closing db')
      self.conn.close()
      self.conn = None

  def GetPlaylistId(self, playlist):
    sql = 'SELECT Playlist_ID AS id from playlists WHERE name = %s'
    self.cursor.execute(sql, (playlist,))
    if self.cursor.rowcount == 1:
      result = self.cursor.fetchone()
      return int(result['id'])
    else:
      return None

  def FromPlaylist(self, playlist, destination_directory, format, cp, m3u):
    # find the playlist id
    playlist_id = self.GetPlaylistId(playlist)
    if playlist_id is None:
      logging.fatal('Unable to find playlist: %s', playlist)

    sel = ', '.join(['tracks.%s as %s' % (x, x) for x in COLUMNS])

    sql = ('SELECT ' + sel + ' FROM tracks, playlist_tracks '
           'WHERE tracks.Track_ID = playlist_tracks.Track_ID '
           'AND playlist_tracks.Playlist_ID = %s;')
    self.cursor.execute(sql, (playlist_id,))
    results = self.cursor.fetchall()
    self.MakeLinksFromLocations(destination_directory,
                                playlist, "Playlist:%s:%s" % (playlist_id,
                                                              playlist),
                                results, format, cp, m3u)


  def FromWhereClause(self,
                      where, destination_directory, name, format, cp, m3u):
    # TODO(ark): make a file with the whereclause in it for Sync
    sql = ('SELECT ' + ','.join(COLUMNS) + ' FROM tracks WHERE %s ' % where)
    self.cursor.execute(sql)
    results = self.cursor.fetchall()

    # TODO(ark): make a name and a description for m3u file
    self.MakeLinksFromLocations(destination_directory,
                                name, None,
                                results, format, cp, m3u)


  def MakeLinksFromLocations(self, destination_directory,
                             name, description,
                             results,
                             format, cp, m3u):
    if self.random_ordering:
      logging.debug('Randomizing playlist')
      random.shuffle(results)

    if format.lower() != 'itunes':
      format = os.path.join(format, '%(number)03d-%(basename)s')
      # make a subdirectory and rename destination_directory
      destination_directory = os.path.join(destination_directory, name)
    else:
      format = None

    if not os.path.exists(destination_directory):
      os.makedirs(destination_directory)

    m3u_file = None
    if m3u and name and description:
      m3u_file = open(os.path.join(destination_directory, name + ".m3u"), "w")
      m3u_file.write("#ITDBDESC:%s\n" % description)

    logging.debug('Making links for %d files in %s',
                  len(results), destination_directory)

    for result in results:
      filename = self.GetFilenameFromResult(result)
      result['number'] = self.number
      result['basename'] = os.path.basename(filename)

      if format:
        link = format % result
      else:
        link = os.path.sep.join(filename.split(os.path.sep)[-3:])
      link = os.path.join(destination_directory, link)
      dir = os.path.dirname(link)

      if not os.path.exists(dir):
        os.makedirs(dir)

      logging.info(link)
      self.number += 1
      if not os.path.exists(link):
        if cp:
          logging.info('Copying %s from %s', os.path.basename(link), filename)
          if not os.path.exists(link):
            shutil.copyfile(filename, link)
        else:
          logging.info('Linking %s from %s', os.path.basename(link), filename)
          os.symlink(filename, link)
      else:
        logging.info('Exists  %s', os.path.basename(link))

      if m3u_file:
        m3u_file.write("#ITDBFILE:%s:%s\n" %
                       (result['Track_ID'], result['Location']))
        m3u_file.write("%s\n" % link[len(destination_directory) + 1:])

    if m3u_file:
      m3u_file.close()
    logging.debug('Done Making links for %d files', len(results))


  def GetFilenameFromResult(self, result):
    """turns a location into a real file location

    Locations look like this:
    file://localhost/Volumes/Data/Music/Sleeper/Smart/03%20Delicious.mp3

    Filenames look like this:
    /Volumes/Data/Music/Sleeper/Smart/03 Delicious.mp3
    """
    # strip of localhost part
    localhost = 'file://localhost'
    location = result['Location']
    if location.startswith(localhost):
      location = location[len(localhost):]
    # url unescape
    return urllib.unquote(location)


  def Sync(self, destination_directory):
    """Make sure a directory is up to date."""
    for filename in os.listdir(destination_directory):
      playlist = os.path.basename(filename)
      playlist_id = self.GetPlaylistId(playlist)
      if playlist_id is None:
        logging.info('Not Syncing: %s', playlist)
      else:
        self.SyncPlaylist(playlist, playlist_id)

  def SyncPlaylist(self, playlist, playlist_id):
    logging.info('Syncing Playlist: %s', playlist)

    # get files in directory


    # get files in playlist

    # work out what's missing

    # remove what's extra

    # write new m3u


def FindUsb():
  paths = ('/Volumes/WTWFDOTCOM',
           '/Volumes/NexusOne')
  for p in paths:
    if os.path.exists(p):
      logging.info('Using USB drive: %s', p)
      return p
  Usage('unable to find any USB drives, perhaps use the --destination option')


def Main():
  """Parse flags, setup logging and go!"""

  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  logging.debug('Starting %s', ' '.join(sys.argv))

  # parse command line options
  try:
    opts, args = getopt.getopt(sys.argv[1:], 'cd:f:hmn:p:rs:uw:',
                               ['copy', 'destination=', 'format=', 'help',
                                'm3u', 'name=', 'playlist=', 'random',
                                'start_number=', 'sync', 'usb', 'where='])
  except getopt.error, msg:
    Usage(msg=msg)

  # Process options

  playlist = None
  dbconfig = os.path.expanduser('~/.itdb.config')
  destination_directory = None
  start_number = 1
  random_ordering = False
  where = None
  name = None
  format = ''
  cp = False
  sync = False
  m3u = False
  for opt, arg in opts:
    if opt in ('-c', '--copy'):
      cp = True
    if opt in ('-d', '--destination'):
      destination_directory = arg
    if opt in ('-f', '--format'):
      format = arg
    if opt in ('-h', '--help'):
      Usage()
    if opt in ('-m', '--m3u'):
      m3u = True
    if opt in ('-n', '--name'):
      name = arg
    if opt in ('-p', '--playlist'):
      playlist = arg
    if opt in ('-r', '--random'):
      random_ordering = True
    if opt in ('-s', '--start_number'):
      start_number = int(arg)
    if opt in ('--sync'):
      sync = True
      if destination_directory is None:
        destination_directory = FindUsb()
    if opt in ('-u', '--usb'):
      if destination_directory is None:
        destination_directory = FindUsb()
      cp = True
      m3u = True
    if opt in ('-w', '--where'):
      where = arg

  if destination_directory is None:
    destination_directory = os.path.expanduser('~/tmp/out')

  pll = PlaylistLinks(dbconfig)
  pll.number = start_number
  pll.random_ordering = random_ordering
  if sync:
    pll.Sync(destination_directory)
  else:
    if playlist:
      pll.FromPlaylist(playlist, destination_directory, format, cp, m3u)
    elif where:
      if not name:
        Usage(msg='You must provide a name when using where')
      else:
        pll.FromWhereClause(where, destination_directory, name,
                            format, cp, m3u)
    else:
      Usage(msg='You must provide a playlist')
    pll.close()
  if os.path.exists(destination_directory):
    cmd = '(cd "%s" && du -Lh -d 1 .)' % destination_directory
    print '\n Disk Size: %s' % cmd
    os.system(cmd)
    print ('\nmkisofs -f -R -J -m .DS_Store -o ~/tmp/disk.iso "%s"' %
           destination_directory)



if __name__ == '__main__':
  Main()
