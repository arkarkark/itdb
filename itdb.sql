-- Created by: Alex K (wtwf.com) Sun Mar  5 10:32:41 2006
-- Copyright 2006 all rights reserved

-- here's the schema for a databse to hold itunes library data

-- I've added a column called User_ID to allow the database to store
-- more than one person's library

-- right now we only store track info and playlist info

-- here's some rough guidelines on making the database with mysql
-- mysqladmin -u root create itdb
-- mysql -u root
-- -- then run these commands
-- CREATE USER itdb;
-- GRANT ALL PRIVILEGES ON itdb.* TO 'itdb'@'localhost' WITH GRANT OPTION;
-- UPDATE mysql.user SET Password = PASSWORD('itdb') WHERE Host IN ('%', 'localhost') AND User = 'itdb';
-- FLUSH PRIVILEGES;

-- once the database is made you can then pass in this file
-- since .itdb.config is in inifile format you can do this
-- cat itdb.sql | mysql --defaults-file= .itdb.config

-- here is the max sizes of my column
--                Album: 75:A Merry Affair - Starbucks Swinging Songs of Red Velvet and Misletoe Kisses
--        Persistent ID: 16:205041DDD52DB022
--         Track Number:  4:2000
--           Track Type:  4:File
--         File Creator: 10:1752133483
--    File Folder Count:  2:-1
--          Disc Number:  1:1
--           Total Time:  8:10794840
--        Play Date UTC: 20:2005-11-29T19:22:17Z
--          Sample Rate:  5:44100
--          Track Count:  5:65535
--                Genre: 25:Ambient,Electronica/Dance
--             Bit Rate:  4:1411
--           Play Count:  3:100
--                 Kind: 24:Protected AAC audio file
--                 Name:175:MegaMix - (Re-Situated)   - from 'Erasure Ultra Rare Trax v.2' CD - This features many samples from 70's tv & cult movies - KROQ Yaz Trance Disco Clark Techno Alternative 80's
--               Artist:110:Catherine Zeta-Jones / Chtchelkanova, Ekaterina / Denise Faye / Goodwin, Deidre / Harrison, Ma / Misner, Susan
--           Disc Count:  1:1
--            File Type: 10:1297106739
--             Track ID:  5:10000
--        Artwork Count:  1:1
--               Rating:  3:100
--        Date Modified: 20:2005-02-21T02:09:02Z
-- Library Folder Count:  2:-1
--                 Year:  5:16665
--           Date Added: 20:2004-08-18T03:24:33Z
--                 Size:  9:111763922
--             Location:313:file://localhost/Volumes/120gig/Music/Yazzoo/Unknown%20Album/07%20MegaMix%20-%20(Re-Situated)%20%20%20-%20from%20'Erasure%20Ultra%20Rare%20Trax%20v.2'%20CD%20-%20This%20features%20many%20samples%20from%2070's%20tv%20&%20cult%20movies%20-%20KROQ%20Yaz%20Trance%20Disco%20Clark%20Techno%20Alternative%2080's%201.mp3

DROP TABLE IF EXISTS tracks;
CREATE TABLE tracks (
User_ID integer(4) NOT NULL,
Track_ID integer(4) NOT NULL,
Name varchar(1024) default '',
Artist varchar(1024) default '',
Album varchar(1024) default '',
Genre varchar(32) default '',
Kind varchar(32) default '',
Size int(4),
Total_Time int(4),
Disc_Number int(1),
Disc_Count int(1),
Track_Number int(2),
Track_Count int(2),
Year int(2),
Date_Modified datetime NOT NULL default '0000-00-00',
Date_Added datetime NOT NULL default '0000-00-00',
Skip_Date datetime NOT NULL default '0000-00-00',
Skip_Count int(1) default 0,
Bit_Rate int(2),
Sample_Rate int(2),
Play_Count int(2),
Play_Date_UTC datetime NOT NULL default '0000-00-00',
Rating int(1) default 0,
Artwork_Count int(1) default 0,
Season int(1),
Persistent_ID varchar(20),
Track_Type varchar(4),
File_Type int(4),
File_Creator int(4),
Location varchar(2048),
File_Folder_Count int(1),
Library_Folder_Count int(1),
PRIMARY KEY (User_ID, Track_ID)
);


DROP TABLE IF EXISTS playlists;
CREATE TABLE playlists (
User_ID integer(4) NOT NULL,
Playlist_ID integer(4) NOT NULL,
Name varchar(1024),
PRIMARY KEY (User_ID, Playlist_ID)
);

DROP TABLE IF EXISTS playlist_tracks;
CREATE TABLE playlist_tracks (
User_ID integer(4) NOT NULL,
Playlist_ID integer(4) NOT NULL,
Track_ID integer(4) NOT NULL,
PRIMARY KEY (User_ID, Playlist_ID, Track_ID)
);

-- how many stars does each playlit have
DROP TABLE IF EXISTS playlist_stats;
CREATE TABLE playlist_stats (
User_ID integer(4) NOT NULL,
Playlist_ID integer(4) NOT NULL,
Rating int(1) default 0,
Count int(4) default 0,
PRIMARY KEY (User_ID, Playlist_ID, Rating)
);


-- example join of the data
-- SELECT t.Name FROM tracks t inner join  playlists p on t.Track_ID = p.Track_ID  WHERE p.Playlist_ID=27884
