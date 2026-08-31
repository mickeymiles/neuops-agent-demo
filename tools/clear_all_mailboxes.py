# -*- coding: utf-8 -*-
"""清空 6 个测试邮箱收件箱（b1/b2/b5/b6 本地模拟角色 + b4 由服务器 009 控制）。

用于分布式联调前清场，避免历史/陈旧任务的 B/D/E/G 邮件干扰新一次全流程。
经 tools/proxy_mail_tunnel.py 的 127.0.0.1:1993/1465 隧道抵达 163。

口令来自环境变量（勿硬编码）：MI1_PASS/MI2_PASS/MI5_PASS/MI6_PASS，B4_PASS 默认已知测试值。
"""
import imaplib
import os
import sys

IMAP_HOST = os.getenv("SMOKE_IMAP_HOST", "127.0.0.1")
IMAP_PORT = int(os.getenv("SMOKE_IMAP_PORT", "1993"))

ACCOUNTS = {
    "b1": ("biquanzhi1@163.com", os.environ.get("MI1_PASS", "")),
    "b2": ("biquanzhi2@163.com", os.environ.get("MI2_PASS", "")),
    "b5": ("biquanzhi5@163.com", os.environ.get("MI5_PASS", "")),
    "b6": ("biquanzhi6@163.com", os.environ.get("MI6_PASS", "")),
    "b4": ("biquanzhi4@163.com", os.environ.get("B4_PASS", "GMydirfgUNnpp87F")),
}


def clear_one(email, pw):
    if not pw:
        print(f"  [skip] {email} 缺口令", flush=True)
        return 0
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(email, pw)
    imaplib.Commands["ID"] = ("AUTH",)
    try:
        imap._simple_command("ID", '("name" "CoTest" "vendor" "NeuOps")')
    except Exception:
        pass
    imap.select("INBOX")
    _, data = imap.search(None, "ALL")
    nums = (data[0] or b"").split()
    n = len(nums)
    if n:
        for num in nums:
            imap.store(num, "+FLAGS", "\\Deleted")
        imap.expunge()
    imap.logout()
    return n


def main():
    total = 0
    for k, (email, pw) in ACCOUNTS.items():
        try:
            n = clear_one(email, pw)
            print(f"  [{k}] {email}: 标记删除 {n} 封", flush=True)
            total += n
        except Exception as e:
            print(f"  [{k}] {email} 清空失败: {e}", flush=True)
    print(f"[done] 共标记删除 {total} 封（163 expunge 可能异步，数秒后可复检）", flush=True)


if __name__ == "__main__":
    main()
