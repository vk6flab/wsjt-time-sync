#!bin/python3
"""Use WSJT-X decode delta_t time offsets to sync system clock through chrony SOCK.

Depends on https://github.com/bmo/py-wsjtx

Normally of course you are reasonably in sync via NTP, but I find when I am offline (e.g.
at a remote field location for POTA) I get out of sync pretty often.  You can reset system 
time manually, but I have had cases where it still drifts out of sync repeatedly and this
disrupts QSO.  It is also more critical to be in sync for FT4 compared to FT8, and FT4 is
frequently useful when trying to run QRP on crowded 20m.

There is a Windows program called JTSync that will handle this, but I didn't find anything
similar for Linux.  You can also handle the offsets separately in JTDX, but I prefer to use
WSJT-X.  You can also use a cheap GPS dongle and gpsd to sync chrony, but it is nice to have
a method that doesn't require extra hardware.  I would like to just use my cellphone GPS time 
for sync, but I haven't found anything that works for that on recent (c2024) Android.

Hence, PyJTSync...  It's currently working although I haven't tested it in the field yet.
It has two major issues: 1) you have to run it sudo to have permission to write to chrony SOCK
and 2) it doesn't handle multicast UDP from WSJT-X correctly so you have to work around that
to avoid blocking GridTracker from receiving the datagrams.  I will try addressing 2) by just
tailing ALL.TXT to get the offsets instead of listening to the UDP stream.  This will also 
avoid dependency on the otherwise nice pywsjtx module.
"""
import argparse
import socket
import struct
import sys
import time
import pywsjtx.extra.simple_server
  
parser = argparse.ArgumentParser(
    prog='PyJTSync',
    description='Use WSJT-X decode delta_t time offsets to sync system clock through chrony SOCK.')
parser.add_argument('-i', '--wsjtx-udp-ip-address', default='127.0.0.1')
parser.add_argument('-p', '--wsjtx-udp-port', default='2237',
                    help='Multicasting is not yet working, so setting this to the WSJT-X UDP port '
                         'will block other programs from receiving packets.  For GridTracker, one '
                         'workaround is to configure GridTracker to forward packets to another port, '
                         'e.g. 2238, and set that port here.')
parser.add_argument('-c', '--chrony-socket', default='/run/chrony.pyjtsync.sock',
                    help='The location of the chrony socket, as defined in its config file via the '
                         'refclock SOCK directive.')
args = parser.parse_args()


def build_chrony_sample(offset):
  epoch_ns = time.time_ns()
  epoch_s = epoch_ns // 1_000_000_000
  plus_us = (epoch_ns % 1_000_000_000) // 1000
  pulse = leap = pad = 0
  chrony_sock_magic = 0x534f434b
  return struct.pack(
      'qqdiiii', epoch_s, plus_us, offset, pulse, leap, pad, chrony_sock_magic)


wsjtx_server = pywsjtx.extra.simple_server.SimpleServer(
        args.wsjtx_udp_ip_address, args.wsjtx_udp_port, timeout=2.0)
chrony_client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
try:
  chrony_client.connect(args.chrony_socket)
except PermissionError:
  message = f'Failed to access {args.chrony_socket}\n'
  message += 'Check that the socket exists and you have write permissions on it.\n'
  message += ('The socket should be created by chronyd on start up, as defined in its '
              'config file via the refclock SOCK directive.')
  raise PermissionError(message) from None

while True:
  pkt, addr_port = wsjtx_server.rx_packet()
  if pkt is None:
    continue

  wsjtx_packet = pywsjtx.WSJTXPacketClassFactory.from_udp_packet(addr_port, pkt)
  if not isinstance(wsjtx_packet, pywsjtx.DecodePacket):
    print(f'Ignoring {wsjtx_packet.__class__.__name__}.')
    continue