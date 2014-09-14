-- Created by: Alex K (wtwf.com) Sun Mar  5 10:32:41 2006
-- Copyright 2006 all rights reserved

-- here's the schema for a databse to hold itunes library data

-- I've added a column called User_ID to allow the database to store
-- more than one person's library

-- right now we only store track info and playlist info

DROP TABLE IF EXISTS tracks;
CREATE TABLE tracks (
User_ID integer(4) NOT NULL,
Track_ID integer(4) NOT NULL,
Name varchar(1024) default '',
Artist varchar(1024) default '',
Album varchar(1024) default '',
Genre varchar(64) default '',
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
Track_Type varchar(8),
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
Playlist_Persistent_ID varchar(1024),
Parent_Persistent_ID varchar(1024),
-- Folder  boolean - how do we do this?
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
