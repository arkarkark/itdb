#!/usr/bin/python
# Copyright 2014 Alex K (wtwf.com)
"""
Make a JXA script to restore an iTunes playlist.

-f: itunes xml file
-p: playlist name (can have multiple -p arguments)

more info:
this makes JXA - Javascript AppleScript
https://github.com/JXA-Cookbook/JXA-Cookbook/wiki/iTunes
Script editor: File -> Open Dictionary then choose iTunes
"""

__author__ = 'wtwf.com (Alex K)'

import getopt
import logging
import os
import sys

import iTunes

def Usage(code, msg=''):
  """Show a usage message."""
  if code:
    fd = sys.stderr
  else:
    fd = sys.stdout
  PROGRAM = os.path.basename(sys.argv[0]) # pylint: disable=invalid-name,unused-variable
  print >> fd, __doc__ % locals()
  if msg:
    print >> fd, msg
  sys.exit(code)

def Main():
  """Run."""
  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  try:
    opts, args = getopt.getopt(sys.argv[1:], 'f:hp:', 'help'.split(','))
  except getopt.error, msg:
    Usage(1, msg)

  if args:
    Usage(1)

  file_name = None
  playlists = []
  for opt, arg in opts:
    if opt in ('-h', '--help'):
      Usage(0)
    if opt in ('-f',):
      file_name = arg
    if opt in ('-p',):
      playlists.append(arg)

  Run(file_name=file_name, playlists=playlists)

def Run(file_name=None, playlists=None):
  if not file_name:
    return Usage(2, "provide a file name")
  if not playlists or len(playlists) == 0:
    return Usage(3, "provide playlist names")

  logging.info("Loading: %r", file_name)
  lib = iTunes.Library(file_name)
  lib.load()
  logging.info("Loaded: %r", file_name)

  track_map = LoadTracks(lib)
  PrintHeader()
  DoPlaylists(lib, playlists, track_map)

def PrintHeader():
  print """#!/usr/bin/osascript -l JavaScript
// -*- JavaScript -*-
var iTunes = Application("iTunes")
iTunes.includeStandardAdditions = true;
"""

def LoadTracks(lib):
  logging.info("Loading tracks")
  track_map = {}
  while True:
    try:
      info = lib.getTrack()
    except EOFError:
      break
    if not info:
      break
    # logging.info("%r", info)
    track_map[info['Track ID']] = {
      'Persistent ID': info[u'Persistent ID'],
      'Name': info[u'Name']
    }
  logging.info("DONE Loading tracks")
  return track_map

def DoPlaylists(lib, playlists, track_map):
  logging.info("Loading playlists")
  while True:
    try:
      info = lib.getPlaylist()
    except EOFError:
      break
    if not info:
      break
    name = info['Name']
    if name in playlists:
      DoPlaylist(info, track_map)
      playlists.remove(name)
      if len(playlists) == 0:
        break
  logging.info("DONE Loading playlists")


def DoPlaylist(playlist, track_map):
  logging.info("Doing playlist: %r", playlist)
  persistent_ids = []
  for track in playlist['Playlist Items']:
    track_id = track['Track ID']
    if track_map.has_key(track_id):
      logging.info(track_map[track_id])
      persistent_ids.append(track_map[track_id]['Persistent ID'])
    else:
      logging.warning("Unable to find track with id: %r", track_id)

  print """var ids = ["%(ids)s"]
var playlist = iTunes.playlists.whose({name: "%(name)s"})[0]
for (trackId of ids) {
  var track = iTunes.tracks.whose({persistentID: trackId})
  if (track && track.length) {
    track.duplicate({to: playlist})
  } else {
    console.log("Failed to find", trackId)
  }
}
  """ % {"name": playlist['Name'], "ids": '", "'.join(persistent_ids)}

if __name__ == '__main__':
  Main()
