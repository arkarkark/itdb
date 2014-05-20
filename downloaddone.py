#!/usr/bin/python
# Copyright 2011 Alex K (wtwf.com) All rights reserved.

"""Run after a mkv file is downloaded. it converts it to m4v and adds it to the iTunes library.
"""

import sys
import os
import datetime
import time

def Main(args):
  out_file = open("/tmp/downloaded.%s.txt" % datetime.date.today().isoformat(),
                  "a")
  out_file.write("Download Done: %r\n" % str(datetime.datetime.now()))
  out_file.write("OLD Args: %r\n" % args)
  print("OLD Args: %r\n" % args)

  args = FixArgs(args)
  out_file.write("NEW Args: %r\n" % args)
  print("NEW Args: %r\n" % args)
  out_file.close()
  file_name = args[1]
  directory_name = args[2]
  other_file_name = args[3]
  if not TryAndConvert(os.path.join(directory_name, file_name)):
    TryAndConvert(os.path.join(directory_name, other_file_name))


def FixArgs(args):
  return [x for x in FixArg(args)]

def FixArg(args, start=0):

  while (start < len(args)):
    end = start
    if args[start].startswith("'"):
      # print "Found ' in %r" % args[start]
      # find the next one that ends with '
      while (end < len(args) and
             not args[end].endswith("'")):
        end += 1
      yield " ".join(args[start:end + 1]).strip("'")
      start = end + 1
    else:
      # print "NO ' in %r" % args[start]
      yield args[start]
      start += 1
    # print "Moving onto %r" % (end + 1)

def TryAndConvert(file_name):
  print 'Trying to convert: %r' % file_name
  if (file_name.lower().endswith(".mkv") and
      os.path.exists(file_name)):
    m4v_file_name = file_name[0:-4] + '.m4v'
    if not os.path.exists(m4v_file_name):
      print "Converting mkv: %r" % file_name
      os.system("/Users/ark/bin/darwin10.0/SublerCLI -i '%s' -o '%s'" %
                (file_name, m4v_file_name))
    print "Loading into iTunes %r" % m4v_file_name
    mac_path = m4v_file_name.replace('/', ':')
    print "mac_path %r" % mac_path
    # os.system("/usr/bin/open -a /Applications/iTunes.app '%s'" %
    #          m4v_file_name)
    # os.systme("""osascript -e 'tell application "iTunes" to pause';""")
    # osascript -e 'tell application "iTunes" to player state as string'
    os.system("""/usr/bin/osascript -e 'tell application "iTunes" to add file "%s" to playlist "Library" of source "Library"'""" % mac_path)
    return True
  return False

if __name__ == '__main__':
  Main(sys.argv)
