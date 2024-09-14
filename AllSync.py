#!/usr/bin/python3
"""Use WSJT-X decode time offsets from ALL.TXT to sync system clock through chrony SOCK.

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

Installation (Fedora 39, but should be similar for other Linux or Mac OS):
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
"""

import argparse
import socket
import struct
import time
from typing import Iterator, TextIO

parser = argparse.ArgumentParser(
    prog='AllSync',
    description='Tail WSJT-X ALL.TXT logfile and use decode delta_t time offsets to sync system '
                'clock through chrony SOCK.')
parser.add_argument('-a', '--all-txt', required=True,
                    help='The path to the WSJT-X ALL.TXT logfile, e.g. ~/WSJT-X/ALL.txt')
parser.add_argument('-c', '--chrony-socket', default='/run/chrony.allsync.sock',
                    help='The location of the chrony socket, as defined in the chrony config '
                         'file via the refclock SOCK directive.')
args = parser.parse_args()


def build_chrony_sample(offset: float) -> bytearray:
  """Build binary message in format expected by chrony SOCK.
  
  Defined in https://github.com/mlichvar/chrony/blob/master/refclock_sock.c
  """
  epoch_ns = time.time_ns()
  epoch_s = epoch_ns // 1_000_000_000
  plus_us = (epoch_ns % 1_000_000_000) // 1000
  pulse = leap = pad = 0
  chrony_sock_magic = 0x534f434b
  return struct.pack(
      'qqdiiii', epoch_s, plus_us, offset, pulse, leap, pad, chrony_sock_magic)


def follow(file: TextIO, sleep_sec: float = 0.1) -> Iterator[str]:
  """Blocking yield lines as they are added to an open file.
  
  If you want to skip preexisting lines, seek the fd to the end before passing.
  """
  line = ''
  while True:
    tmp = file.readline()
    if not tmp:
      time.sleep(sleep_sec)  # Sleep to avoid excessive CPU usage.
      continue
    line += tmp
    if not line.endswith('\n'):
      continue
    yield line
    line = ''


chrony_client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
try:
  chrony_client.connect(args.chrony_socket)
except PermissionError:
  message = f'Failed to access {args.chrony_socket}\n'
  message += 'Check that the socket exists and you have write permissions on it.\n'
  message += ('The socket should be created by chronyd on start up, as defined in its '
              'config file via the refclock SOCK directive.')
  raise PermissionError(message) from None

print(f'Waiting for decodes to log in {args.all_txt}...')
with open(args.all_txt) as f:
  f.seek(0, 2)  # Skip existing decodes; seek to the end.
  for line in follow(f):
    offset = -float(line.split()[5])
    sample = build_chrony_sample(offset)
    print(f'Forwarding sample with offset {offset} to chrony SOCK {args.chrony_socket}.')
    chrony_client.sendall(sample)

    # Chrony won't accept more than one sample with the same timeval, so sleep for
    # one microsecond to ensure all the decode offsets will be considered.
    time.sleep(0.000_001)