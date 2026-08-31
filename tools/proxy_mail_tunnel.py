#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 CONNECT 隧道转发器：把 127.0.0.1 端口透传到真实服务器，经由 HTTP 代理的 CONNECT。

用于受限网络（无直连 TCP，仅能走 HTTP 代理且代理允许 CONNECT）下，
让本机代码以为自己在直连 127.0.0.1:1993 / 127.0.0.1:1465，实际流量经代理到达
imap.163.com:993 / smtp.163.com:465。配合 tests/ont_smoke_real.py 的
SMOKE_IMAP_*/ONT_MAIL_IMAP_* 环境变量即可在受限环境跑真实邮箱冒烟。

环境变量：
  PROXY_HOST / PROXY_PORT   HTTP 代理地址（默认 127.0.0.1:49945）

用法：
  python3 tools/proxy_mail_tunnel.py
"""
import http.client
import os
import socket
import threading
import time

PROXY_HOST = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("PROXY_PORT", "49945"))

# (本地绑定, 远端真实地址)
FORWARDS = [
    (("127.0.0.1", 1993), ("imap.163.com", 993)),
    (("127.0.0.1", 1465), ("smtp.163.com", 465)),
]


def tunnel(client: socket.socket, remote):
    try:
        p = http.client.HTTPConnection(PROXY_HOST, PROXY_PORT, timeout=60)
        p.set_tunnel(remote[0], remote[1])
        p.connect()  # 发送 CONNECT 并读取 200
        upstream = p.sock
    except Exception as e:
        print(f"[tunnel] CONNECT {remote[0]}:{remote[1]} 失败: {e}", flush=True)
        try:
            client.close()
        except Exception:
            pass
        return

    def pipe(a, b):
        try:
            while True:
                data = a.recv(65536)
                if not data:
                    break
                b.sendall(data)
        except Exception:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    s.close()
                except Exception:
                    pass

    t1 = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
    t2 = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
    t1.start()
    t2.start()


def serve(bind, remote):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(bind)
    s.listen(64)
    print(f"[serve] {bind[0]}:{bind[1]} -> {remote[0]}:{remote[1]}", flush=True)
    while True:
        c, _ = s.accept()
        threading.Thread(target=tunnel, args=(c, remote), daemon=True).start()


if __name__ == "__main__":
    for bind, remote in FORWARDS:
        threading.Thread(target=serve, args=(bind, remote), daemon=True).start()
    print("[main] 隧道转发器已启动，Ctrl-C 退出", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("[main] 退出", flush=True)
