Mediacenter-in-a-box
====================

The idea here is that there's a single Compose file with stuff. The stuff comprises the
following:

## Two mountpoints

There are two mountpoints here:

* The `downloads` mountpoint, where downloads are placed.
* The `media` mountpoint, where all the media is.

## Three steps

There are three steps:

First, qTorrent downloads the files into the `downloads` mountpoint. That mountpoint
contains three directories, `incomplete`, `complete`, and `renamed`. qBittorrent
downloads files into the `incomplete` directory, and, when it's done, it moves them into
the `complete` directory. A few minutes later, those files are OK to delete, so you can
set qBittorrent to delete the files when done seeding.

Then, Filebot hardlinks the files from `complete` to `renamed`, with the final FS
structure that will go into the `media` mountpoint. These files are now ready to
transfer to the `media` mountpoint. This is done by a `transfer.sh` script that you
should put in the `filebot` Harbormaster data directory. Your script can delete the
files in the source when done.

Finally, the files are scanned and displayed by Jellyfin.

## Considerations

If you have multiple media directories, you can use `unionfs` or `mergefs` to mount them
on the `media` mountpoint as one. This is good to do anyway so that you can merge the
local `renamed` directory with the (perhaps remote) `media` mountpoint, so Jellyfin can
see the files immediately on download, without waiting to transfer them to the media
directory.
