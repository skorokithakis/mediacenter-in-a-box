Mediacenter-in-a-box
====================

The Mediacenter-in-a-box is a single, Harbormaster-compatible deployment that includes
all the applications you need to set up a media center server.

It includes:

* Jellyfin (to play your media)
* Ombi (so you can request media)
* Sonarr (to manage your shows)
* Radarr (to manage your movies)
* Bazarr (to download subtitles)
* Prowlarr (to manage your trackers)
* SABnzbd (to download from Usenet)
* qBittorrent (to download with BitTorrent)

To get this running with Harbormaster, all you need is the following configuration:

```yaml
apps:
  mediacenterbox:
    url: https://github.com/skorokithakis/mediacenter-in-a-box.git
    environment:
      JELLYFIN_PublishedServerUrl: https://<your jellyfin URL>
    replacements:
      MEDIA_DIR: /your/media/dir
```

You'll then need your own ingress server to get TLS and nice-looking hostnames (Caddy is
recommended because of its simplicity).
The ports you'll need to forward are:

* Jellyfin: 53539
* Ombi: 55542
* Sonarr: 10087
* Radarr: 59982
* Bazarr: 10044
* Prowlarr: 57045
* SABnzbd 40184
* qBittorrent: 35944

That should be it for the initial setup! You can access your apps on the hostnames you
selected, and start configuring.

---

THE BELOW IS SLIGHTLY OUT OF DATE.

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
