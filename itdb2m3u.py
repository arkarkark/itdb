#!/usr/bin/python
# Created by: Alex K (wtwf.com) Sat Mar  4 09:15:22 2006
# Copyright 2009 all rights reserved

"""Make a m3u file for every playlist in the itdb database

Usage: %(PROGRAM)s [options]

Options:
  -h/--help
    Print this message and exit

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



if __name__ == '__main__':
  began = str(datetime.datetime.today())
  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  logging.debug("Starting %s @ %s", " ".join(sys.argv), began)

  try:
    opts, args = getopt.getopt(sys.argv[1:], 'h',
                               ['help'])
  except getopt.error, msg:
    usage(1, msg)

  if args:
    usage(1)

  config = ConfigParser.ConfigParser()
  config.read(['itdb.config.m3u',
               '/export/arkstuff/ark/.itdb.config.m3u',
               os.path.expanduser('~ark/.itdb.config.m3u')])

  it = itdb2html.iTunesDbToHtml(config)

  for opt, arg in opts:
    if opt in ('-h', '--help'):
      usage(0)

  it.Connect()
  it.WritePlaylistsAsM3u()
  logging.debug("Started @ %s", began)
  logging.debug("Done    @ %s", str(datetime.datetime.today()))
