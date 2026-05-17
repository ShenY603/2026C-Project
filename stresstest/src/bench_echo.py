# bench_echo.py
import socket
import time
from concurrent.futures import ThreadPoolExecutor

HOST, PORT = "118.24.46.231", 8080   # 云公网 IP
CONNS, MSG, DURATION = 20, b"x" * 256, 30   # 先 20 连接、30 秒

def recv_all(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

def worker():
    n = 0
    try:
        s = socket.create_connection((HOST, PORT), timeout=10)
        s.settimeout(10)
        end = time.time() + DURATION
        while time.time() < end:
            s.sendall(MSG)
            data = recv_all(s, len(MSG))
            if data is None or len(data) != len(MSG):
                break
            n += 1
        s.close()
    except OSError:
        pass
    return n

t0 = time.time()
with ThreadPoolExecutor(max_workers=CONNS) as ex:
    total = sum(ex.map(lambda _: worker(), range(CONNS)))
elapsed = time.time() - t0
print(f"connections={CONNS}, duration={DURATION}s, total_roundtrips={total}, "
      f"approx_qps={total/elapsed:.0f}")