#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK Copyright 2022 Alex K (wtwf.com)

"""Move Music.app playlists from one computer to another."""

__author__ = "wtwf.com (Alex K)"

import argparse
import atexit
import collections
import datetime
import logging
import os
import subprocess
import sys
import time

import appscript
import argcomplete
import humanize
import tqdm


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
            delta = datetime.datetime.now() - start
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
        print("\nRuntimes:\n", file=sys.stdout)
        for desc, deltas in LogRuntime.RUNTIMES.items():
            duration = ", ".join([humanize.naturaldelta(delta) for delta in deltas])
            print(f"{desc}: {duration}", file=sys.stdout)


atexit.register(LogRuntime.show_runtimes)


class ShutdownHandler(logging.Handler):
    def emit(self, record):
        logging.shutdown()
        sys.exit(1)


@LogRuntime()
def main():
    """Parse args and do the thing."""
    logging.basicConfig()
    logging.getLogger().addHandler(ShutdownHandler(level=50))

    print("Getting playlist/folder names")
    music = appscript.app("Music")
    pls = music.playlists()
    playlists_names = [p.name() for p in pls if p.special_kind() == appscript.k.none]
    folder_names = [p.name() for p in pls if p.special_kind() == appscript.k.folder]
    print("done")

    parser = argparse.ArgumentParser(description="Program to do the thing.")
    parser.add_argument(
        "-p",
        "--prefix",
        default=os.path.expanduser("~/Music/Music/"),
        help="prefix file location",
    )
    parser.add_argument(
        "-a",
        "--allfilename",
        default="all.m3u",
        help="name of m3u file containing all files to sync",
    )
    parser.add_argument(
        "--every",
        action="store_true",
        help="Export every playlist",
    )
    parser.add_argument(
        "--dest",
        default="",
        help="rsync like destination for files in playlist",
    )
    parser.add_argument("-size", "--size", help="Size", type=int)
    parser.add_argument("-q", "--quiet", help="Log verbosely", action="store_true")
    parser.add_argument("-d", "--debug", help="Log debug messages", action="store_true")
    parser.add_argument(
        "-e",
        "--export",
        help="export playlists to m3u file and copy music to dest",
        action="store_true",
    )
    parser.add_argument(
        "-i", "--import", help="import playlists from m3u files", nargs="+"
    )
    parser.add_argument(
        "--playlists", help="playlist names", choices=playlists_names, nargs="+"
    )
    parser.add_argument(
        "--folders", help="folder names to export", choices=folder_names, nargs="+"
    )
    parser.add_argument(
        "--no-add",
        action="store_false",
        default=True,
        dest="add",
        help="Don't actually add files to playlist",
    )

    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.INFO)
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Start")

    if args.export or args.every or args.folders:
        if args.every:
            items = playlists_names
        else:
            items = args.playlists or get_selected_playlist(music)

        if args.folders:
            for folder in args.folders:
                items.extend(get_playlists_in_folder(music, folder))

        with open(args.allfilename, "a", encoding="utf-8") as allfile:
            for item in items:
                export_playlist(music, args.prefix, allfile, item)

        if args.dest:
            cmd = [
                os.path.expandvars("$HOMEBREW_PREFIX/bin/rsync"),
                "--iconv=utf-8",
                "-Phav",
                "--files-from",
                args.allfilename,
                args.prefix,
                args.dest,
            ]
            print(" ".join(cmd))
            subprocess.call(cmd)

    elif getattr(args, "import"):
        for item in getattr(args, "import"):
            import_playlist(music, args.add, args.prefix, item)
            time.sleep(10)
    else:
        logging.fatal("you either need to import or export")


def get_playlists_in_folder(music, folder):
    parent = get_playlist_by_name(music, folder)
    return [x.name() for x in music.playlists() if get_playlist_parent(x) == parent]


def get_selected_playlist(music):
    sel = music.selection()
    if not sel:
        return []
    playlist = sel[0].container()
    return [playlist.name()]


def get_playlist_by_name(music, name):
    return (music.playlists[appscript.its.name == name]() or [None])[0]


def get_playlist_parent(playlist):
    try:
        return playlist.parent()
    except:
        return None


def export_playlist(music, prefix, allfile, name):
    logging.info("Making Playlist: %s", name)

    playlist = get_playlist_by_name(music, name)
    tracks = playlist.tracks()

    m3u_filename = os.path.abspath(f"{playlist.name()}.m3u")
    with open(m3u_filename, "w", encoding="utf-8") as m3ufile:
        for track in tqdm.tqdm(tracks):
            logging.debug("%s", track.name())
            location = track.location()
            if location:
                path = location.path[len(prefix) :]
                m3ufile.write(f"{path}\n")
                allfile.write(f"{path}\n")
            else:
                logging.warning("FILE NOT FOUND: %s", track.name())
    return m3u_filename


def import_playlist(music, add, prefix, m3ufilename):
    playlist_name = os.path.splitext(os.path.basename(m3ufilename))[0]
    logging.info("importing: %s", playlist_name)

    playlist = get_playlist_by_name(music, playlist_name)
    if playlist:
        logging.info("Playlist already exists")
        # TODO get tracks already in playlist....
    else:
        logging.info("Making playlist: %r", playlist_name)
        lib_name = "Music"
        library = music.playlists[appscript.its.name == lib_name]()[0]
        playlist = library.make(new=appscript.k.playlist)
        playlist.name.set(playlist_name)

    logging.info("Opening m3u file")
    toadd = []
    with open(m3ufilename, encoding="utf-8") as m3ufile:
        for filename in m3ufile:
            filename = filename.strip()
            if filename and filename[0] == "/":
                filename = filename[1:]

            fullfilename = os.path.join(prefix, filename)
            if os.path.exists(fullfilename):
                logging.info("exists : %s", filename)
                toadd.append(appscript.mactypes.File(fullfilename))
            else:
                logging.info("MISSING: %s", filename)
        logging.info(
            "Adding %d songs to Music.app playlist %s", len(toadd), playlist_name
        )
        if add:
            music.add(
                toadd,
                to=playlist,
            )


if __name__ == "__main__":
    main()
