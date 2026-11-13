"""[ADDED] Sim-only Xsens/GMR 35D reference bridge, isolated from SONIC.

Reads HumDex's opt-in, TTL-protected Redis key, and forwards only fresh frames
as timestamped binary UDP to TWIST2 sim policy. Never sends robot commands.
"""
import argparse
import json
import math
import socket
import struct
import time

import redis

KEY = "twist2_xsens_sim:reference"
PACKET = struct.Struct('<d35f')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--redis-host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=9892)
    args = ap.parse_args()
    if args.port == 5556 or args.port in (9880, 9881):
        ap.error('port conflicts with SONIC / TWIST2 state ports')
    db = redis.Redis(host=args.redis_host, port=6379, socket_timeout=0.2)
    db.ping()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = ('127.0.0.1', args.port)
    last_ts = -1
    print(f'[bridge] Redis {KEY} -> UDP {dest}; SIM ONLY', flush=True)
    try:
        while True:
            try:
                raw = db.get(KEY)
                if raw:
                    obj = json.loads(raw)
                    ts = int(obj['timestamp_ms'])
                    vals = obj['body_35']
                    if (ts > last_ts and len(vals) == 35
                            and all(math.isfinite(float(v)) for v in vals)
                            and abs(time.time() * 1000 - ts) < 400):
                        sock.sendto(PACKET.pack(time.monotonic(), *(float(v) for v in vals)), dest)
                        last_ts = ts
            except (redis.RedisError, ValueError, KeyError, TypeError, struct.error) as e:
                print(f'[bridge-warning] {e}', flush=True)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == '__main__':
    main()
