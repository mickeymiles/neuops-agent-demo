# -*- coding: utf-8 -*-
"""批量导入知识库脚本

用法：
    python3 -m scripts.build_kb                      # 交互式（选择知识库 + 指定文件/目录）
    python3 -m scripts.build_kb --kb 知识库名 --dir ./docs
    python3 -m scripts.build_kb --kb 知识库名 --files a.pdf b.docx c.xlsx
    python3 -m scripts.build_kb --bind emp-004       # 把已有知识库绑定到员工

说明：
    - 需要先通过管理页创建知识库，或用 --create 直接创建
    - 文件会复制到 uploads/{kb_id}/ 目录统一管理
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, knowledge  # noqa: E402

SUPPORTED = {".txt", ".md", ".xlsx", ".pdf", ".docx"}


def collect_files(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, names in os.walk(p):
                for n in names:
                    if os.path.splitext(n)[1].lower() in SUPPORTED:
                        files.append(os.path.join(root, n))
        elif os.path.isfile(p) and os.path.splitext(p)[1].lower() in SUPPORTED:
            files.append(p)
    return sorted(files)


def pick_kb(create_name=None):
    kbs = db.db_list_knowledge_bases()
    if not kbs:
        print("当前没有知识库，请先用管理页新建，或使用 --create")
        return None
    print("\n现有知识库：")
    for i, k in enumerate(kbs):
        print(f"  [{i}] {k['name']} (文档{k['doc_count']}/块{k['chunk_count']})")
    if create_name:
        for k in kbs:
            if k["name"] == create_name:
                return k
    try:
        idx = int(input("选择编号: ").strip())
        return kbs[idx]
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="批量导入知识库")
    parser.add_argument("--kb", help="知识库名称（必须已存在）")
    parser.add_argument("--create", help="新建知识库名称")
    parser.add_argument("--desc", default="", help="知识库描述")
    parser.add_argument("--dir", help="从目录导入")
    parser.add_argument("--files", nargs="*", help="从文件列表导入")
    parser.add_argument("--bind", help="导入后绑定到员工 id（如 emp-004）")
    args = parser.parse_args()

    kb = None
    if args.create:
        kb_id = db.db_create_knowledge_base(args.create, args.desc)
        kb = db.db_get_knowledge_base(kb_id)
        print(f"已创建知识库: {args.create} ({kb_id})")
    else:
        kb = pick_kb(args.kb)
        if not kb:
            sys.exit(1)

    files = []
    if args.dir:
        files += collect_files([args.dir])
    if args.files:
        files += collect_files(args.files)
    if not files and not args.bind:
        print("未指定文件，退出")
        sys.exit(1)

    if files:
        # 复制到 uploads 目录
        target = knowledge.get_upload_dir(kb["id"])
        copied = []
        for f in files:
            dst = os.path.join(target, os.path.basename(f))
            if os.path.abspath(f) != os.path.abspath(dst):
                shutil.copy2(f, dst)
            copied.append(dst)
        print(f"解析 {len(copied)} 个文件并构建索引...")
        result = knowledge.build_kb_index(kb["id"], copied)
        print(f"完成: 文档{result['doc_count']} / 切块{result['chunk_count']} / 向量{'是' if result['vector'] else '否(降级关键词)'}")

    if args.bind:
        ids = db.db_get_employee_kb_ids(args.bind) + [kb["id"]]
        db.db_bind_employee_kb(args.bind, ids)
        print(f"已绑定员工 {args.bind} -> {kb['name']}")


if __name__ == "__main__":
    main()
