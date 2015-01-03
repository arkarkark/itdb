# itdb - iTunes Database and utilities

itdb will load all the data from iTunes into a MySQL database.
Once you have the data in your database you can do some fun stuff with it.

playlistlinks will make symbolic links and m3u files for your playlists.
itdb2html is a super old crusty, crufty web-ui for your music

# Database Setup

Copy the config file and install mysql (I like [brew](http://brew.sh/)).

```bash
brew install mysql
mysql.server.start

cp itdb.config.example ~/.itdb.config
# maybe you want to edit ~/.itdb.config now?
mysqladmin -u root create itdb
mysql -u root
```

Then run these commands (you might want to change the password (and in ~/.itdb.config too):
```sql
CREATE USER itdb;
GRANT ALL PRIVILEGES ON itdb.* TO 'itdb'@'localhost' WITH GRANT OPTION;
UPDATE mysql.user SET Password = PASSWORD('itdb') WHERE Host IN ('%', 'localhost') AND User = 'itdb';
FLUSH PRIVILEGES;
```

Once the database is made you can then create the database using itdb.sql
(since .itdb.config is in inifile format you can use --defaults-file) and then load your data:
```bash
mysql --defaults-file=~/.itdb.config < itdb.sql
# did that work?
mysql --defaults-file=~/.itdb.config <<< 'SHOW TABLES'
# load it
./itdbloader.py
# verify it works
mysql --defaults-file=~/.itdb.config -E <<< 'SELECT COUNT(*) AS num_tracks FROM tracks; SELECT COUNT(*) AS num_playlisys FROM playlists;' | fgrep -v '*****'
```

## Packages

Here's what I had to do on my mac to get things working.

```bash
sudo easy_install pip cheetah
sudo pip install MySQL-python
```

## itdbloader.py

I found iTunes.py over at lazycat.org (no longer available there)
which I've modified to also load playlist as well as track
information. It uses the most excellent pulldom python API which
attempts to be more memory efficient than loading the whole dom into
memory.

The XML says it's UTF-8 put pulldom gets confused when it found some
characters in it so I made it 'sanitize' the XML by stripping out
non-ASCII characters, I know this isn't strictly a good thing, but
I'll spend more time on that once I have it working more (I said that in 2006...).

### options

-m show the maximum size of each column - useful for adjusting column sizes in itdb.sql
-n do not clear the database and the auto generated cache files
-f force the loading even if the .xml file is older than the stat file

# playlistlinks.py

This utility will make a nest of symlinks of your playlists. This is
very useful to make CD's of playlists, or copy them to your Android
phone.

## Usage

`playlistlinks.py --help` will tell you all the command line options,
I'll take you through some use cases.

`playlistlinks.py -p 'My Favorite Music'` will make symlinks in
~/tmp/out for your playlist called My Favorite Music. You can then use
mkisofs to make a burnable cd/dvd image (mkisofs commands are printed
by playlistlinks.py).

`./playlistlinks.py -f iTunes --folder '4+'` will take all the
playlists under a folder called `4+` in your iTunes app and make
symlinks for all the files under there. It will retain the iTunes
directory structure which means that files will not be duplicated. You
can take this output in ~/tmp/out and rsync it to antoher machine,
copy over your iTunes library files and then fire up iTunes and the
iTunes on that machine will be able to play the playlists you copied
over. I use this to sync the best parts of my iTunes library to
another machine.

The `-f` or `--format` option allow you to specify how the symlinks are created. You can use % type formatting and reference any information from a file. e.g.
` -f '%(Genre)s/%(Artist)s-%(Album)s'` will make a files like this
`Rock/ACDC-Back in Black/001-Hells Bells.mp3`. Note that -f is just for the directory name. The trackname and a playlist index are added by playlistlinks.

You can also randomize the track ordering and create m3u files.

You can provide multiple playlist and folder options on the command
line and it will make links for all of them. You can also tell it to
make m3u files for whatever files are currently in the destination
folder. This is useful to sync only part of your library, but make all
your playlists (but only include files that were synced).

Here's how I use it to sync music to my Moto-X phone:

```
  ./playlistlinks.py -m -d /tmp/pl/phone -f iTunes \
    --folder 'Awesome' \
    --nonewmusic \
    --folder 'Shuffles' \
    --folder "MP3's CD's" \
    --folder "Eclectic Music" \
    --folder 'SFW' \
    --folder '4+' \
```

This makes links for all my music in the playlists under Awesome
(about 8Gig of 161Gig total). Then I make m3u files for all my
playlists under those other categories (without copying any more music
files).  Then I use adbrsync.py from
[android-tools](https://github.com/jsharkey/android-tools) to copy
these to my phone: `adbrsync.py /tmp/pl/phone /sdcard/Music`. Now I
can use [RocketPlayer](https://play.google.com/store/apps/details?id=com.jrtstudio.AnotherMusicPlayer) to play my music!

#itdb2html

Sorry to fizzle out at the end, itdb2html is a super old janky way to
make webpages about your library. I really should re-implement it
using AngularJS but I just don't have a need for it anymore.

The overview page is interesting to see which artists you like and
much music of each genre you have. I also like the distribution of
ratings display.
