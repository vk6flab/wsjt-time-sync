# About
Use WSJT-X decode time offsets from ALL.TXT to sync system clock through chrony SOCK.

Digital radio modes like FT8 require system time to be at least coarsely in sync.
Normally of course you can stay in sync via NTP, but I find when I am offline (e.g. at a 
remote field location for POTA) I get out of sync pretty often.  You can reset system time 
manually (chronyc manual on; chronyc settime; chronyc makestep ...), but I have had cases 
where it still drifts out of sync repeatedly and disrupts QSOs.  It is also more critical to
be in sync for FT4 compared to FT8, and FT4 is frequently useful when trying to run QRP on 
crowded 20m.

There is a Windows program called JTSync that will sync system time based on decode offsets, 
but I didn't find anything similar for Linux / Mac OS.  You can handle the offsets separately
in JTDX, but I prefer to use WSJT-X.  You can also use a cheap GPS dongle and gpsd to sync 
chrony, but it is nice to have a method that doesn't require extra hardware.  I found an 
Android app that allows forwarding cellphone NMEA to gpsd over UDP 
(https://play.google.com/store/apps/details?id=com.kikimanjaro.nmea_to_network), but I haven't
gotten that working end-to-end and it requires keeping the phone awake.

Hence: AllSync, a very simple Python script that tails WSJT-X's ALL.TXT log, extracts the decode
offsets, and sends them to chronyc SOCK to keep time synced.  This is working well in field tests.
As an alternative to watching the ALL.TXT file, you can connect to WSJT-X's UDP socket, but that 
is a bit more involved and I  didn't yet get multicasting working so it would conflict with other
applications that listen to UDP (e.g. GridTracker).

# Installation
## Installation (Fedora 39, but should be similar for other Linux or Mac OS):
Add a line to the chronyd config file (e.g. /etc/chrony.conf):

    refclock SOCK /run/chrony.allsync.sock refid WSJT precision 1e-1 offset 0.0000


Then restart chronyd and the socket should be created:

    sudo systemctl restart chronyd
    sudo ls -l /run/chrony.allsync.sock


Usage (run as root to have access to the SOCK):

    sudo python3 AllSync.py --all-txt ~/WSJT-X/ALL.TXT
    

Then as decodes are added to ALL.TXT you should get terminal messages from AllSync and you
should see the chrony source start pinging:

    watch chronyc sources


# Credit
This code comes from a gist written by @chinasaur (Peter H. Li)

