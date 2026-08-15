"""研发专家 emp-005 的文件工具（直接读写 9006 系统代码）"""

from .config import DEV_9006_ROOT, DEV_ALLOWED_SUBDIRS


def _resolve_dev_path(path: str) -> str:
    """解析路径并限制在 9006 项目目录内，防止越界访问"""
    import pathlib
    root = pathlib.Path(DEV_9006_ROOT).resolve()
    p = pathlib.Path(path)
    if p.is_absolute():
        target = p.resolve()
    else:
        target = (root / p).resolve()
    # 必须在 root 内，且属于允许的子目录
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError(f"路径越界：{path} 不在 {DEV_9006_ROOT} 内")
    return target


def _dev_list_files() -> dict:
    import pathlib
    files = []
    for sub in DEV_ALLOWED_SUBDIRS:
        d = pathlib.Path(DEV_9006_ROOT) / sub
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and not f.name.endswith((".pyc", ".db", ".xlsx")):
                files.append(str(f.relative_to(DEV_9006_ROOT)))
    return {"files": files, "count": len(files)}


def _dev_read_file(path: str, offset: int = 1, limit: int = 200) -> dict:
    """读取文件，返回带行号内容，支持 offset 分页"""
    target = _resolve_dev_path(path)
    if not target.is_file():
        return {"error": f"文件不存在：{path}"}
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"读取失败：{e}"}
    lines = content.splitlines()
    total = len(lines)
    start = max(1, offset)
    end = min(total, start + limit - 1)
    if start > total:
        return {"error": f"offset {offset} 超出文件总行数 {total}"}
    numbered = "\n".join(f"{start + i:4d}| {line}" for i, line in enumerate(lines[start - 1:end]))
    result = {"path": path, "total_lines": total, "offset": start, "limit": limit,
              "truncated": end < total, "content": numbered}
    if end < total:
        result["hint"] = f"已显示第 {start}-{end} 行，共 {total} 行，可用 offset 继续读取"
    return result


def _fuzzy_edit_replace(content: str, old_string: str, new_string: str):
    """精确匹配优先；失败后行级空白归一化模糊匹配。返回 (new_content, status, count)"""
    # 1. 精确匹配
    if old_string in content:
        cnt = content.count(old_string)
        if cnt == 1:
            return content.replace(old_string, new_string, 1), "success", 1
        return content, "multiple", cnt
    # 2. 模糊匹配：按行 strip 归一化定位
    old_lines = old_string.split("\n")
    content_lines = content.split("\n")
    if len(old_lines) < 2:
        return content, "not_found", 0
    norm = lambda s: s.strip()
    old_norm = [norm(l) for l in old_lines]
    n = len(old_lines)
    matches = []
    for i in range(len(content_lines) - n + 1):
        if [norm(l) for l in content_lines[i:i + n]] == old_norm:
            matches.append(i)
    if not matches:
        return content, "not_found", 0
    if len(matches) > 1:
        return content, "multiple", len(matches)
    i = matches[0]
    # 缩进继承：新内容首行继承匹配窗口首行缩进，其余行保持相对缩进
    first = content_lines[i]
    base_indent = first[:len(first) - len(first.lstrip())]
    new_lines = new_string.split("\n")
    if not new_lines:
        new_lines = [""]
    new_first_indent = new_lines[0][:len(new_lines[0]) - len(new_lines[0].lstrip())]
    out = []
    for nl in new_lines:
        nl_indent = nl[:len(nl) - len(nl.lstrip())]
        rel = len(nl_indent) - len(new_first_indent)
        out.append(" " * max(0, len(base_indent) + rel) + nl.lstrip())
    new_content = "\n".join(content_lines[:i] + out + content_lines[i + n:])
    return new_content, "success", 1


def _dev_edit_file(path: str, old_string: str, new_string: str) -> dict:
    """局部替换：old_string → new_string。支持模糊匹配（容忍空白/缩进差异），改前自动备份。"""
    target = _resolve_dev_path(path)
    if not target.is_file():
        return {"error": f"文件不存在：{path}"}
    import time as _t
    content = target.read_text(encoding="utf-8", errors="replace")
    new_content, status, count = _fuzzy_edit_replace(content, old_string, new_string)
    if status == "not_found":
        return {"error": "old_string 在文件中未找到（含空白归一化后），请先 read_code_file 确认原文"}
    if status == "multiple":
        return {"error": f"old_string 匹配到 {count} 处，请提供更长的上下文使其唯一"}
    # 备份
    bak = str(target) + ".bak." + _t.strftime("%Y%m%d_%H%M%S")
    try:
        import shutil
        shutil.copy2(str(target), bak)
    except Exception:
        bak = None
    target.write_text(new_content, encoding="utf-8")
    return {"path": path, "status": "success", "backup": bak,
            "changed_lines": new_string.count("\n") - old_string.count("\n") + 1}


def _dev_search_code(query: str, file_glob: str = None, max_results: int = 30) -> dict:
    """按关键词搜索代码内容，返回匹配的文件、行号、行内容"""
    import fnmatch
    import pathlib
    results = []
    for sub in DEV_ALLOWED_SUBDIRS:
        d = pathlib.Path(DEV_9006_ROOT) / sub
        if not d.exists():
            continue
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            if "__pycache__" in f.parts or f.name.endswith((".pyc", ".db", ".xlsx")):
                continue
            if file_glob and not fnmatch.fnmatch(f.name, file_glob):
                continue
            rel = str(f.relative_to(DEV_9006_ROOT))
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if query in line:
                    results.append({"file": rel, "line": i, "content": line.strip()[:200]})
                    if len(results) >= max_results:
                        return {"matches": results, "count": len(results), "truncated": True}
    return {"matches": results, "count": len(results), "truncated": False}


def _dev_write_new_file(path: str, content: str) -> dict:
    """新建文件：仅在文件不存在时写入，限定在允许子目录内"""
    import pathlib
    target = _resolve_dev_path(path)
    rel = target.relative_to(pathlib.Path(DEV_9006_ROOT).resolve())
    if not rel.parts or rel.parts[0] not in DEV_ALLOWED_SUBDIRS:
        return {"error": f"只允许在 {DEV_ALLOWED_SUBDIRS} 子目录内新建文件"}
    if target.exists():
        return {"error": f"文件已存在：{path}，请用 edit_code_file 做局部修改，不要覆盖"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"path": path, "status": "success", "bytes": len(content.encode('utf-8'))}


SHELL_ALLOWED_CMDS = ("git", "pytest", "ls")
SHELL_ALLOWED_GIT_SUB = ("status", "diff", "log", "branch", "--version")


def _dev_run_shell(command: str) -> dict:
    """执行白名单只读/验证类命令，工作目录锁定 9006 项目根"""
    import shlex
    import subprocess
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return {"error": f"命令解析失败：{e}"}
    if not parts:
        return {"error": "命令为空"}
    cmd = parts[0]
    if cmd not in SHELL_ALLOWED_CMDS:
        return {"error": f"命令 {cmd} 不在白名单，仅允许：{', '.join(SHELL_ALLOWED_CMDS)}"}
    if cmd == "git":
        if len(parts) < 2 or parts[1] not in SHELL_ALLOWED_GIT_SUB:
            return {"error": f"git 仅允许只读子命令：{', '.join(SHELL_ALLOWED_GIT_SUB)}"}
    try:
        r = subprocess.run(parts, cwd=DEV_9006_ROOT, shell=False,
                           capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"error": "命令执行超时（30s）"}
    except Exception as e:
        return {"error": f"命令执行失败：{e}"}
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if len(out) > 4000:
        out = out[:4000] + "\n...(输出截断)"
    return {"command": command, "returncode": r.returncode,
            "stdout": out, "stderr": err[:1000]}


DEV_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_project_files",
            "description": "列出9006经营业务展示系统的代码文件（backend后端、frontend前端、docs文档），了解项目结构。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_code_file",
            "description": "读取9006项目指定文件的代码内容（带行号）。path 为相对路径如 backend/main.py 或 frontend/index.html。可用 offset/limit 分页。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 backend/main.py"},
                    "offset": {"type": "integer", "description": "从第几行开始读（默认1）"},
                    "limit": {"type": "integer", "description": "最多读多少行（默认200）"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_code_file",
            "description": "对9006项目文件做局部替换修改：把 old_string 替换为 new_string，支持模糊匹配（容忍空白/缩进差异）。改前自动备份。old_string 尽量与原文一致且唯一。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 frontend/index.html"},
                    "old_string": {"type": "string", "description": "要替换的原文（必须精确匹配文件内容）"},
                    "new_string": {"type": "string", "description": "替换后的新内容"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "按关键词搜索9006项目代码内容，定位相关逻辑所在文件与行号。query 为要搜索的字符串；file_glob 可选，如 *.py 或 index.html；max_results 默认30。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要搜索的关键词或字符串，如「gross_margin」或「签单毛利率」"},
                    "file_glob": {"type": "string", "description": "文件名过滤，如 *.py、*.html，可空"},
                    "max_results": {"type": "integer", "description": "最多返回条数，默认30"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_new_file",
            "description": "在9006项目内新建文件。path 为相对路径（必须在 backend/frontend/docs 子目录内）；content 为完整文件内容。仅当文件不存在时可用，已存在的文件请用 edit_code_file。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，如 frontend/new_page.html"},
                    "content": {"type": "string", "description": "新建文件的完整内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "执行白名单只读/验证命令（git status/diff/log、pytest、ls），用于查看代码改动、跑测试验证。工作目录锁定9006项目根，禁止写操作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令，如 git diff、git status、git log --oneline、pytest backend/test_x.py、ls"},
                },
                "required": ["command"],
            },
        },
    },
]


async def execute_dev_tool(name: str, args: dict) -> dict:
    """执行研发专家文件工具"""
    try:
        if name == "list_project_files":
            return _dev_list_files()
        if name == "read_code_file":
            path = args.get("path", "")
            offset = max(1, int(args.get("offset", 1) or 1))
            limit = max(1, int(args.get("limit", 200) or 200))
            return _dev_read_file(path, offset, limit)
        if name == "edit_code_file":
            return _dev_edit_file(args.get("path", ""), args.get("old_string", ""), args.get("new_string", ""))
        if name == "search_code":
            return _dev_search_code(args.get("query", ""), args.get("file_glob", ""), int(args.get("max_results", 30) or 30))
        if name == "write_new_file":
            return _dev_write_new_file(args.get("path", ""), args.get("content", ""))
        if name == "run_shell":
            return _dev_run_shell(args.get("command", ""))
        return {"error": f"未知工具 {name}"}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"工具执行失败: {e}"}


def _tool_result_summary(fn: str, result: dict) -> dict:
    """构造工具返回结果摘要，供前端「观测快照」展示真实数据"""
    s = {"tool": fn}
    if not isinstance(result, dict):
        s["result"] = str(result)[:200]
        return s
    for k in ("count", "column_count", "total"):
        if result.get(k) is not None:
            s["count"] = result[k]
            break
    if "headers" in result:
        s["headers"] = result["headers"]
    if "rows" in result and result["rows"]:
        s["sample"] = result["rows"][:2]
    if "tables" in result:
        s["tables"] = result["tables"]
    if "columns" in result and isinstance(result["columns"], list):
        s["columns"] = [c.get("name", c) if isinstance(c, dict) else c for c in result["columns"]]
    if "metrics" in result:
        s["metrics_count"] = len(result["metrics"])
    if "error" in result:
        s["error"] = result["error"]
    return s


