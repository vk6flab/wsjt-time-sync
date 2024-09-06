#!bin/python3
"""Use WSJT-X decode delta_t time offsets from ALL.TXT to sync system clock through chrony SOCK.

Normally of course you are reasonably in sync via NTP, but I find when I am offline (e.g.
at a remote field location for POTA) I get out of sync pretty often.  You can reset system 
time manually, but I have had cases where it still drifts out of sync repeatedly and this
disrupts QSOs.  It is also more critical to be in sync for FT4 compared to FT8, and FT4 is
frequently useful when trying to run QRP on crowded 20m.

There is a Windows program called JTSync that will handle this, but I didn't find anything
similar for Linux.  You can also handle the offsets separately in JTDX, but I prefer to use
WSJT-X.  You can also use a cheap GPS dongle and gpsd to sync chrony, but it is nice to have
a method that doesn't require extra hardware.  (I would like to just use my cellphone GPS time 
for sync, but I haven't found anything that works for that on recent (ca. 2024) Android.)

Hence, AllSync...  This is currently working although I haven't tested it in the field yet.
It probably needs to be run as root in order to access the chrony SOCK.
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
  line = ''
  while True:
    tmp = file.readline()
    if not tmp:
      time.sleep(sleep_sec)
      continue
    line += tmp
    if not line.endswith('\n'):
      continue
    yield line
    line = ''


chrony_client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
try:
  pass
  chrony_client.connect(args.chrony_socket)
except PermissionError:
  message = f'Failed to access {chrony_socket}\n'
  message += 'Check that the socket exists and you have write permissions on it.\n'
  message += ('The socket should be created by chronyd on start up, as defined in its '
              'config file via the refclock SOCK directive.')
  raise PermissionError(message) from None

print(f'Waiting for decodes to log in {args.all_txt}...')
with open(args.all_txt) as f:
  f.seek(0, 2)
  for line in follow(f):
    offset = float(line.split()[5])
    sample = build_chrony_sample(offset)
    print(f'Forwarding sample with offset {offset} to chrony SOCK {args.chrony_socket}.')
    chrony_client.sendall(sample)

    # Chrony won't accept more than one sample with the same timeval, so sleep for
    # one microsecond to ensure all the decode offsets will be considered.
    time.sleep(0.000_001)