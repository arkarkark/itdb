#!/usr/bin/python

"""Find the dupes from a bunch of playlist links

sum out/*/* | sort -n >dupes
"""

import os

def main():
  last_sum = -1
  for line in open("dupes"):
    this_sum = int(line.split(" ", 1)[0])
    if last_sum == this_sum:
      file_name = line.split(" ", 2)[2].rstrip()
      print file_name
      # os.unlink(file_name)
    last_sum = this_sum

if __name__ == '__main__':
  main()



