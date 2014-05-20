#!/usr/bin/python
"""
Find dupe files based on music content (even after id3 tags have been edited).



fgrep '<key>Location</key>' ~/Music/iTunes/iTunes\ Library.xml >keys.xml
fgrep localhost/Volumes/Data keys.xml | wc -l

~/mysrc/itdb/dupes
09:13 ark@retina#fgrep localhost/Users/ark/Music/iTunes/iTunes%20Media keys.xml | wc -l

~/mysrc/itdb/dupes
09:13 ark@retina#fgrep localhost keys.xml | wc -l


before:

22496 /Volumes/Data
17154 /Users/ark/Music/iTunes/iTunes%20Media
  477 /Users/ark/Music/Data
 1540 %201.mp3 - possible dupes
  267 %202.mp3 - possible dupes?
"""


import collections
import hashlib
import io
import json
import logging
import os
import re
import sys
import urllib

files_file_name = 'files.dat'
files = collections.defaultdict(dict)
checksums_file_name = 'checksums.dat'
checksums = collections.defaultdict(list)

CHECKSUM_SIZE = 100000 # take a checksum of the last 100,000 bytes


def LoadFiles():
  count = 0
  if not os.path.exists(files_file_name):
    return
  logging.info('Loading Files...')
  with open(files_file_name) as file_obj:
    for line in file_obj:
      try:
        count += 1
        x = json.loads(line)
        if 'location' in x:
          files[x['location']] = x
          if 'checksum' in x:
            checksums[x['checksum']].append(x['location'])
      except Exception as e:
        logging.error('error with line: %r', line)
  logging.info('Loaded %d files', count)

def SaveFiles():
  SaveFile(files_file_name, files)
  SaveFile(checksums_file_name, checksums)
  logging.info('Done Saving Files.')

def SaveFile(file_name, dict_obj):
  logging.info('Saving File; %s', file_name)
  with open(file_name, 'w') as file_obj:
    for v in dict_obj.values():
      try:
        file_obj.write(json.dumps(v) + '\n')
      except Exception as e:
        logging.error('Unable to save %r', v)

def LoadPlaylistFiles(file_name):
  logging.info('Loading Playlist Files')
  # go through all files and unset the iTunes bi
  logging.info('resetting iTunes Present Keys')
  for f in files.values():
    f.pop('iTunes', None)

  count = 0
  with open(file_name) as file_obj:
    for line in file_obj:
      count += 1
      if count % 5000 == 0:
        logging.info('Loading playlist: %d', count)
      ans = re.search('localhost([^<]*)', line)
      if ans:
        location = urllib.unquote(ans.group(1))
        if location not in files:
          logging.error('%r is in playlists but not files!', location)
        files[location]['iTunes'] = True
        CheckFile(location)
      else:
        print 'no match: ' + line
  logging.info('Done loading %d playlist files', count)

def FindAllFiles(dir_name):
  logging.info('finding all files under: %s', dir_name)
  count = 0
  for root, dirs, fs in os.walk(dir_name):
    for f in fs:
      count += 1
      location = os.path.join(root, f)
      files[location]['location'] = location
      files[location]['exists'] = True
      CheckFile(location)
      # TODO(ark) add mtime, sha256sum of whole file, non-id3 part
      if count % 5000 == 0:
        logging.info(count)

def CheckFile(location):
  try:
    st = os.stat(location)
    mtime = st.st_mtime
    size = st.st_size
  except OSError:
    files[location]['exists'] = False
    return
  if mtime == files[location].get('mtime'):
    # file not modified since last checked
    return
  files[location]['mtime'] = mtime
  if size > CHECKSUM_SIZE:
    checksum = GetCheckSum(location)
    if checksum:
      files[location]['checksum'] = checksum
      checksums[checksum].append(location)

def GetCheckSum(location):
  try:
    f_obj = open(location)
    f_obj.seek(0, io.SEEK_END)
    f_obj.seek(f_obj.tell() - CHECKSUM_SIZE, io.SEEK_SET)
    m = hashlib.sha256()
    m.update(f_obj.read(CHECKSUM_SIZE))
    return str(m.hexdigest())
  except Exception as e:
    logging.error('unable to get checksum of %r because of %r', location, e)
    return None


def SimilarFiles(f):
  base = re.sub(r' [0-9]+\.mp3$', '.mp3', f)
  if base != f:
    yield base
  (root, ext) = os.path.splitext(base)
  for x in range(1, 10):
    n = '%s %d%s' % (root, x, ext)
    if n != f:
      yield n


def FindDupes():
  for f in files.values():
    if not f.get('iTunes'):
      continue
    dupes = []
    location = f['location']
    for comp in SimilarFiles(location):
      if comp in files:
        if files[comp].get('iTunes'):
          dupes.append(comp + ' ***')
        else:
          dupes.append(comp)
    if dupes:
      logging.info('\nfound dupes for %s\n%s',
                   location, '\n'.join(dupes))


def Main():
  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  LoadFiles()
  #  os.system("""fgrep '<key>Location</key>' \
  #                 ~/Music/iTunes/iTunes\ Library.xml >keys.xml""")
  FindAllFiles('/Users/ark/Music/Data')
  FindAllFiles('/Volumes/Data/Music')
  LoadPlaylistFiles('keys.xml')
  SaveFiles()
  FindDupes()


if __name__ == '__main__':
  Main()
