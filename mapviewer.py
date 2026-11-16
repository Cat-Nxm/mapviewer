#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mapviewer —— 读懂 map 文件：到底是谁占了我的 Flash 和 RAM

支持:
  * GCC (arm-none-eabi-ld) 生成的 .map
  * Keil / armcc (armlink) 生成的 .map

用法:
  python mapviewer.py firmware.map
  python mapviewer.py firmware.map -n 30
  python mapviewer.py firmware.map --kind ram
  python mapviewer.py firmware.map --by module
  python mapviewer.py firmware.map --html report.html

设计原则:
  1. 只用标准库, 不装任何东西就能跑。
  2. 默认输出按"符号"看, 因为定位问题时你找的是函数名。
  3. 同时告诉你"谁占的"和"是不是你自己写的" —— 库占大头是最常见的真相。
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# 数据结构
# --------------------------------------------------------------------------


@dataclass
class Entry:
    """map 文件里的一条记录: 某个目标文件的某个段占了多少空间"""

    section: str          # 段名, 例如 .text.main / .bss
    addr: int             # 起始地址
    size: int             # 字节数
    obj: str              # 来源文件, 例如 ./build/main.o 或 libc.a(memcpy.o)
    kind: str = ""        # flash / ram / meta / other, 解析后统一判定

    @property
    def symbol(self) -> str:
        """.text.main -> main ; .bss -> .bss"""
        s = self.section
        if s.startswith(".") and s.count(".") >= 2:
            name = s.split(".", 2)[2]
            if name.startswith("startup."):
                name = name[len("startup."):]
            return name
        return s

    @property
    def module(self) -> str:
        """去掉路径和归档前缀, 只留文件名: ./Core/Src/main.o -> main.o"""
        o = self.obj
        if "(" in o and o.endswith(")"):
            o = o[o.index("(") + 1 : -1]
        return Path(o).name

    @property
    def is_lib(self) -> bool:
        """来自静态库归档(.a / .lib)的, 算库; 否则算你自己的代码"""
        return "(" in self.obj and self.obj.endswith(")")


@dataclass
class Memory:
    """链接脚本里声明的存储器区域"""

    name: str
    origin: int
    length: int


@dataclass
class Result:
    entries: list[Entry] = field(default_factory=list)
    discarded: list[Entry] = field(default_factory=list)   # 被 --gc-sections 丢掉的段
    memories: list[Memory] = field(default_factory=list)
    declared: dict[str, tuple[int, int]] = field(default_factory=dict)  # 段名 -> (大小, 起始地址)
    fmt: str = ""

    @property
    def total(self) -> int:
        return sum(e.size for e in self.entries)

    def declared_of(self, kind: str) -> int:
        total = 0
        for name, (size, addr) in self.declared.items():
            k = kind_of(name)
            if k == "other":
                k = mem_kind(self.memories, addr)
            if k == kind:
                total += size
        return total


# --------------------------------------------------------------------------
# 段归类: 一个段到底占 Flash 还是 RAM
# --------------------------------------------------------------------------

FLASH_PREFIX = (
    ".text", ".rodata", ".isr_vector", ".init", ".fini", ".preinit_array",
    ".init_array", ".fini_array", ".ARM", ".eh_frame", ".glue", ".vectors", ".data.rel.ro",
)
RAM_PREFIX = (".bss", ".data", ".noinit", ".heap", ".stack", ".ccmram", "COMMON")
META_PREFIX = (".debug", ".comment", ".ARM.attributes", ".note", ".symtab", ".strtab",
               ".rel", ".gnu", ".group", ".stab")


def kind_of(section: str) -> str:
    s = section
    if s.startswith("COMMON"):
        return "ram"
    for p in META_PREFIX:
        if s.startswith(p):
            return "meta"      # 调试/元信息, 不占 Flash 也不占 RAM
    for p in FLASH_PREFIX:
        if s.startswith(p):
            return "flash"
    for p in RAM_PREFIX:
        if s.startswith(p):
            return "ram"
    return "other"


# --------------------------------------------------------------------------
# 解析: GCC
# --------------------------------------------------------------------------

RE_GCC_MEM = re.compile(r"^(\S+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)")
# 一行式:  " .text.main   0x0800014c   0x2  path/obj.o"
RE_GCC_ONE = re.compile(r"^\s+(\S+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+(\S.*)$")
# 续行式:  "                0x0800014c   0x2  path/obj.o"   (段名在上一行)
RE_GCC_CONT = re.compile(r"^\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+(\S.*)$")
# 只有段名, 没有地址:  " .text.SystemInit"
RE_GCC_NAME_ONLY = re.compile(r"^\s+(\.[\w.$-]+)\s*$")
# 输出段表头(顶格, 没有目标文件):  ".text   0x0800010c   0x1480"
RE_GCC_HEADER = re.compile(
    r"^(\.[\w.$-]+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)(\s+load address.*)?\s*$")
RE_GCC_OBJ = re.compile(r"(\.o$|\.obj$|\.a\(|\.lib\()")


def _scan_sections(lines: list[str]) -> tuple[list[Entry], list[tuple[str, int, int]]]:
    """扫一段 map 文本, 返回 (输入段条目, 输出段表头)

    输入段可能是两行(段名单独一行, 地址在下一行), 所以要记住 pending。
    """
    entries: list[Entry] = []
    headers: list[tuple[str, int, int]] = []
    pending = ""
    for l in lines:
        if not l.strip():
            continue

        h = RE_GCC_HEADER.match(l)
        if h:
            headers.append((h.group(1), int(h.group(3), 16), int(h.group(2), 16)))
            continue

        m = RE_GCC_NAME_ONLY.match(l)
        if m:
            pending = m.group(1)
            continue

        m = RE_GCC_ONE.match(l)
        if m:
            section, addr, size, rest = (
                m.group(1), int(m.group(2), 16), int(m.group(3), 16), m.group(4).strip())
        else:
            m = RE_GCC_CONT.match(l)
            if m and pending:
                section = pending
                addr, size, rest = int(m.group(1), 16), int(m.group(2), 16), m.group(3).strip()
                pending = ""
            else:
                pending = ""
                continue

        if not RE_GCC_OBJ.search(rest):
            continue          # 符号赋值 / 链接脚本指令, 不是目标文件
        entries.append(Entry(section, addr, size, rest.split()[0]))
    return entries, headers


def parse_gcc(text: str) -> Result:
    res = Result(fmt="gcc")
    lines = text.splitlines()

    # 1) Memory Configuration
    try:
        i = next(i for i, l in enumerate(lines) if l.startswith("Memory Configuration"))
    except StopIteration:
        i = 0
    for l in lines[i:]:
        if not l.strip():
            if res.memories:
                break
            continue
        if l.lower().startswith(("name", "origin", "attributes")):
            continue
        m = RE_GCC_MEM.match(l.strip())
        if m and not l.startswith(" "):
            res.memories.append(Memory(m.group(1), int(m.group(2), 16), int(m.group(3), 16)))

    # 2) 主体: "Linker script and memory map" 之后
    #    (前面的 "Discarded input sections" 都是被 gc-sections 丢掉的, 地址全是 0)
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("Linker script and memory map"))
    except StopIteration:
        start = 0

    res.entries, headers = _scan_sections(lines[start:])
    for name, size, addr in headers:
        old = res.declared.get(name, (0, 0))
        res.declared[name] = (old[0] + size, old[1] or addr)

    # 3) 单独记下被丢弃的段, 供 --discarded 用
    d_start = None
    for i, l in enumerate(lines):
        if l.startswith("Discarded input sections"):
            d_start = i
            break
    if d_start is not None:
        d_end = len(lines)
        for i in range(d_start + 1, len(lines)):
            if lines[i].startswith("Memory Configuration"):
                d_end = i
                break
        res.discarded, _ = _scan_sections(lines[d_start:d_end])

    # 4) 合并同名同源, 去掉 0 字节
    res.entries = _merge([e for e in res.entries if e.size > 0])
    res.discarded = _merge([e for e in res.discarded if e.size > 0])
    finalize(res)
    return res


# --------------------------------------------------------------------------
# 解析: armcc / armlink (Keil)
# --------------------------------------------------------------------------

RE_ARM_IN = re.compile(
    r"^\s+0x([0-9a-fA-F]{8})\s+0x([0-9a-fA-F]{8})\s+0x([0-9a-fA-F]+)\s+"
    r"(\w+)\s+(\w+)\s+(\d+)\s+(\S+)\s+(\S+)"
)
RE_ARM_REGION = re.compile(
    r"Execution Region (\S+) \(Exec base: 0x[0-9a-fA-F]+, Load base: 0x[0-9a-fA-F]+, "
    r"Size: 0x[0-9a-fA-F]+, Max: 0x([0-9a-fA-F]+)"
)


def parse_armcc(text: str) -> Result:
    res = Result(fmt="armcc")
    got = False
    for l in text.splitlines():
        m = RE_ARM_IN.match(l)
        if m:
            got = True
            res.entries.append(
                Entry(m.group(7), int(m.group(1), 16), int(m.group(3), 16), m.group(8))
            )
            continue
        # Keil 的 map 没有 Memory Configuration 块, 容量藏在 Execution Region 行里
        r = RE_ARM_REGION.search(l)
        if r:
            name, cap = r.group(1), int(r.group(2), 16)
            if cap and cap < 0xFFFFFFFF:
                res.memories.append(Memory(name, 0, cap))
    if got:
        res.entries = _merge([e for e in res.entries if e.size > 0])
    finalize(res)
    return res


# --------------------------------------------------------------------------
# 公共
# --------------------------------------------------------------------------


def _merge(entries: list[Entry]) -> list[Entry]:
    """同段名 + 同目标文件的记录合并(有些链接器会拆成多行)"""
    bucket: dict[tuple[str, str], Entry] = {}
    for e in entries:
        key = (e.section, e.obj)
        if key in bucket:
            bucket[key].size += e.size
        else:
            bucket[key] = e
    return list(bucket.values())


def mem_kind(memories: list, addr: int) -> str:
    for m in memories:
        if m.length >= 0xFFFFFFFF:
            continue
        if m.origin <= addr < m.origin + m.length:
            n = m.name.upper()
            if any(x in n for x in ("FLASH", "ROM", "IROM")):
                return "flash"
            if any(x in n for x in ("RAM", "CCM")):
                return "ram"
    return "other"


def finalize(res: "Result") -> None:
    """给每条记录定归属: 先看段名, 看不出来就看它的地址落在哪个存储器里。
    这样 .rtt_buffer / ._user_heap_stack 这类自定义段也能算对。"""
    for e in list(res.entries) + list(res.discarded):
        k = kind_of(e.section)
        if k == "other":
            k = mem_kind(res.memories, e.addr)
        e.kind = k


def detect(text: str) -> str:
    if "Linker script and memory map" in text:
        return "gcc"
    if "Memory Map of the image" in text or "Image Symbol Table" in text:
        return "armcc"
    return ""


def parse(path: Path) -> Result:
    text = path.read_text(encoding="utf-8", errors="replace")
    fmt = detect(text)
    if fmt == "gcc":
        return parse_gcc(text)
    if fmt == "armcc":
        return parse_armcc(text)
    raise SystemExit(
        "认不出这个 map 文件的格式。\n"
        "目前支持 GCC(ld) 和 Keil(armlink) 两种。\n"
        "如果是别家的链接器, 把文件发我, 我加一个解析器。"
    )


def human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.2f} MB"


def _w(s: str) -> int:
    """显示宽度: 中日韩字符算 2 个字符宽"""
    return sum(2 if ord(c) > 0x1100 and not (0x2000 <= ord(c) <= 0x206F) else 1 for c in s)


def pad(s: str, width: int, align: str = "left") -> str:
    """按显示宽度补空格, 保证中英混排也能对齐"""
    gap = max(0, width - _w(s))
    if align == "right":
        return " " * gap + s
    return s + " " * gap


def bar(ratio: float, width: int = 24) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def _supports(ch: str) -> bool:
    """当前控制台能不能显示这个字符(cp936 下 █ 会炸)"""
    try:
        ch.encode(sys.stdout.encoding or "ascii")
        return True
    except Exception:
        return False


BAR_FULL, BAR_EMPTY = ("█", "░") if (_supports("█") and _supports("░")) else ("#", "-")
WARN = "⚠" if _supports("⚠") else "[!]"


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------


def pick_memory(res: Result, kind: str) -> Memory | None:
    for m in res.memories:
        n = m.name.upper()
        if kind == "flash" and any(k in n for k in ("FLASH", "ROM", "CODE", "IROM")):
            return m
        if kind == "ram" and any(k in n for k in ("RAM", "IRAM", "CCM")):
            return m
    return None


def report(res: Result, top: int, by: str, kind: str) -> str:
    out: list[str] = []
    w = out.append

    entries = res.entries
    if kind != "all":
        entries = [e for e in entries if e.kind == kind]

    if not entries:
        return "没有解析到任何条目, 检查一下 map 文件是不是空的, 或者段名规则要不要补充。"

    total = sum(e.size for e in entries)

    w("")
    w(f"  格式        {res.fmt}")
    w(f"  条目        {len(entries)} 条")
    w(f"  合计        {human(total)}")
    w("")

    # 空间占用条
    # 空间占用条 (有链接器声明的大小时, 以它为准)
    for k in ("flash", "ram"):
        sub = [e for e in entries if e.kind == k]
        if not sub:
            continue
        used = res.declared_of(k) or sum(e.size for e in sub)
        mem = pick_memory(res, k)
        cap = mem.length if mem else None
        if cap:
            r = used / cap
            w(f"  {k.upper():<6}{human(used):>10} / {human(cap):<10} {r * 100:5.1f}%  {bar(r, 30)}")
        else:
            w(f"  {k.upper():<6}{human(used):>10}  (map 里没有声明容量)")

    # 解析完整性校验: 链接器自己声明的段大小, 和解析出来的合计对不上就是漏了
    merged_note = False
    for k in ("flash", "ram"):
        decl = res.declared_of(k)
        if not decl:
            continue
        got = sum(e.size for e in res.entries if e.kind == k)
        diff = decl - got
        if diff == 0:
            mark = "✓"
        elif abs(diff) <= 64:
            mark = f"差 {abs(diff)} B (链接器对齐填充, 正常)"
        elif diff > 0:
            mark = f"{WARN} 差 {diff} B, 可能有未归类的段"
        else:
            mark = f"{WARN} 输入段比声明多 {-diff} B (链接器合并了重复内容, 正常)"
            merged_note = True
        w(f"  {'校验':<6}{k.upper()}  链接器 {human(decl):>9} / 解析 {human(got):>9}  {mark}")
    if merged_note:
        w("  注      上面的 Top 榜按输入段统计, 字符串合并(--merge-constants / relax)")
        w("          会让同内容被列多次, 所以排名合计可能大于总量。总量以链接器为准。")

    # 按模块聚合
    if by == "module":
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for e in entries:
            agg[e.module][0 if e.kind == "flash" else 1] += e.size
        rows = sorted(agg.items(), key=lambda kv: -(kv[1][0] + kv[1][1]))[:top]
        tf = sum(v[0] for v in agg.values()) or 1
        tr = sum(v[1] for v in agg.values()) or 1
        w("")
        w("  " + pad("#", 3, "right") + "  " + pad("Flash", 10, "right")
          + "  " + pad("RAM", 10, "right") + "  模块")
        w("  " + "-" * 70)
        for i, (name, (f, rr)) in enumerate(rows, 1):
            w("  " + pad(str(i), 3, "right") + "  " + pad(human(f), 10, "right")
              + "  " + pad(human(rr), 10, "right") + "  " + name)
        w("")
        w("  " + pad("", 5) + pad("合计", 10, "right") + "  " + pad(human(tf), 10, "right")
          + "  " + pad(human(tr), 10, "right"))
        return "\n".join(out) + "\n"

    # 按符号排序 (占比是在各自存储器内部的占比)
    totals = {k: (sum(e.size for e in entries if e.kind == k) or 1) for k in ("flash", "ram")}
    rows = sorted(entries, key=lambda e: -e.size)[:top]
    w("")
    head = ("  " + pad("#", 3, "right") + "  " + pad("大小", 10, "right")
            + "  " + pad("占比", 6, "right"))
    if kind == "all":
        head += "  " + pad("内存", 5)
    w(head + "  " + pad("符号", 30) + "  来源")
    w("  " + "-" * (96 if kind == "all" else 90))
    for i, e in enumerate(rows, 1):
        src = e.module + ("  [lib]" if e.is_lib else "")
        pct = e.size / totals.get(e.kind, total) * 100
        line = ("  " + pad(str(i), 3, "right") + "  " + pad(human(e.size), 10, "right")
                + "  " + pad(f"{pct:.1f}%", 6, "right"))
        if kind == "all":
            line += "  " + pad("Flash" if e.kind == "flash" else "RAM", 5)
        w(line + "  " + pad(e.symbol[:30], 30) + "  " + src)
    if kind == "all":
        w("")
        w("  占比 = 在该存储器内部的占比。Flash 总量 " + human(totals["flash"])
          + ", RAM 总量 " + human(totals["ram"]) + "。")
        w("  只看一种: -k flash  或  -k ram")

    # 自己写的 vs 库
    lib = sum(e.size for e in entries if e.is_lib)
    mine = total - lib
    w("")
    w("  谁在占地方:")
    w(f"    我的代码  {human(mine):>10}  {mine / total * 100:5.1f}%  {bar(mine / total)}")
    w(f"    静态库    {human(lib):>10}  {lib / total * 100:5.1f}%  {bar(lib / total)}")
    if lib > mine:
        w("")
        w(f"  {WARN} 库比你自己的代码占得多。这是嵌入式的常态, 但也是最大的优化空间:")
        w("    换 newlib-nano / 关掉 printf 浮点 / 去掉没用的重定向, 常常能省下几十 KB。")
    return "\n".join(out) + "\n"


def to_html(res: Result, top: int, title: str) -> str:
    entries = sorted(res.entries, key=lambda e: -e.size)[:top]
    total = res.total or 1
    rows = []
    for e in entries:
        pct = e.size / total * 100
        rows.append(
            "<tr>"
            f"<td class='sym'>{html.escape(e.symbol)}</td>"
            f"<td class='num'>{human(e.size)}</td>"
            f"<td class='barcell'><div class='bar' style='width:{max(pct, 0.4):.2f}%'></div>"
            f"<span class='pct'>{pct:.1f}%</span></td>"
            f"<td class='src'>{html.escape(e.module)}{' <em>[lib]</em>' if e.is_lib else ''}</td>"
            "</tr>"
        )
    cards = []
    for k in ("flash", "ram"):
        sub = [e for e in res.entries if e.kind == k]
        used = sum(e.size for e in sub)
        mem = pick_memory(res, k)
        if not used:
            continue
        cap = mem.length if mem else 0
        pct = used / cap * 100 if cap else 0
        cards.append(
            f"<div class='card'><div class='k'>{k.upper()}</div>"
            f"<div class='v'>{human(used)}</div>"
            f"<div class='s'>of {human(cap) if cap else '?'} · {pct:.1f}%</div></div>"
        )
    return f"""<!doctype html>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body{{font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;color:#22303a;
   background:#faf8f5;margin:0;padding:40px 6vw;}}
 h1{{font-size:22px;margin:0 0 4px;letter-spacing:.5px}}
 .sub{{color:#8b8b8b;margin-bottom:28px;font-size:13px}}
 .cards{{display:flex;gap:16px;margin-bottom:32px;flex-wrap:wrap}}
 .card{{background:#fff;border:1px solid #e6e0d8;border-radius:10px;padding:16px 20px;min-width:160px}}
 .card .k{{font-size:11px;letter-spacing:2px;color:#a08a6f}}
 .card .v{{font-size:22px;font-weight:600;margin:2px 0}}
 .card .s{{font-size:12px;color:#999}}
 table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e6e0d8;border-radius:10px;overflow:hidden}}
 th{{text-align:left;font-size:12px;color:#8b8b8b;font-weight:500;padding:10px 14px;background:#f3efe8;
   border-bottom:1px solid #e6e0d8}}
 td{{padding:8px 14px;border-bottom:1px solid #f2eee8;vertical-align:middle}}
 tr:last-child td{{border-bottom:none}}
 .sym{{font-family:Consolas,Menlo,monospace;font-size:13px;color:#1b333b}}
 .num{{text-align:right;white-space:nowrap;color:#4a5b66}}
 .src{{font-family:Consolas,monospace;font-size:12px;color:#8b8b8b}}
 .barcell{{width:38%;position:relative;min-width:180px}}
 .bar{{height:8px;border-radius:4px;background:linear-gradient(90deg,#8c5a3b,#c08a5e);min-width:2px}}
 .pct{{position:absolute;right:14px;top:8px;font-size:12px;color:#a08a6f}}
 em{{color:#c08a5e;font-style:normal;font-size:11px}}
 .foot{{margin-top:22px;color:#aaa;font-size:12px}}
</style>
<h1>{html.escape(title)}</h1>
<div class="sub">mapviewer · {len(res.entries)} 条记录 · 合计 {human(res.total)}</div>
<div class="cards">{''.join(cards)}</div>
<table>
<tr><th>符号</th><th style="text-align:right">大小</th><th>占比</th><th>来源</th></tr>
{''.join(rows)}
</table>
<div class="foot">由 mapviewer 生成 · 只读 map 文件, 不改动任何工程</div>
"""


# --------------------------------------------------------------------------
# 被丢弃的段
# --------------------------------------------------------------------------


def discarded_report(res: Result, top: int = 12) -> str:
    out: list[str] = []
    w = out.append

    if not res.discarded:
        return "\n  这份 map 里没有 Discarded input sections(可能没开 --gc-sections, 或是 armcc)。\n"

    code = [e for e in res.discarded if e.kind == "flash"]
    data = [e for e in res.discarded if e.kind == "ram"]
    dbg = [e for e in res.discarded if e.kind == "meta"]
    s_code = sum(e.size for e in code) + sum(e.size for e in data)
    s_dbg = sum(e.size for e in dbg)
    s_all = sum(e.size for e in res.discarded)

    w("")
    w("  丢弃清单   Discarded input sections")
    w("")
    w(f"  条目        {len(res.discarded)} 条")
    w(f"  总计        {human(s_all)}")
    w(f"    代码      {human(s_code):>10}   ← 真正被裁掉的程序")
    w(f"    调试信息  {human(s_dbg):>10}   不进 Flash, 可以忽略")
    w("")

    # 按模块
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for e in res.discarded:
        slot = 1 if e.kind == "meta" else 0
        agg[e.module][slot] += e.size
    rows = sorted(agg.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:top]

    w("  丢弃最多的模块")
    w("    " + pad("#", 3, "right") + "  " + pad("代码", 10, "right")
      + "  " + pad("调试", 10, "right") + "  模块")
    w("    " + "-" * 66)
    for i, (m, (c, d)) in enumerate(rows, 1):
        w("    " + pad(str(i), 3, "right") + "  " + pad(human(c), 10, "right")
          + "  " + pad(human(d), 10, "right") + "  " + m)
    w("")

    # 整个模块都没用上
    kept = {e.module for e in res.entries if e.kind != "meta"}
    libs = {e.module for e in res.discarded if e.is_lib}
    dead = [(m, c) for m, (c, d) in agg.items() if c > 0 and m not in kept and m not in libs]
    if dead:
        dead.sort(key=lambda kv: -kv[1])
        w(f"  整个文件一行都没进固件 ({len(dead)})")
        for m, c in dead[:top]:
            w(f"    {human(c):>10}  {m}")
        w("")

    if dead:
        w("      上表里 HAL 模块(stm32xxxx_hal_*)可以在 hal_conf.h 里关掉, 省编译时间;")
        w("      其他文件被整体丢弃, 说明对应功能没启用(例如 syscalls.c 没了 = printf 没重定向)。")
        w("")
    w("  注  Discarded 不是浪费, 是裁剪生效的证据。")
    w("      唯一要担心的是: 只被向量表/函数指针/汇编间接引用的东西被误丢。")
    w("      用 -Wl,--print-gc-sections 可以看到完整清单。")
    w("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# 两个版本对比
# --------------------------------------------------------------------------


def _agg(entries: list[Entry]) -> dict[tuple[str, str], int]:
    d: dict[tuple[str, str], int] = defaultdict(int)
    for e in entries:
        d[(e.module, e.symbol)] += e.size
    return d


def _agg_mod(entries: list[Entry]) -> dict[str, int]:
    d: dict[str, int] = defaultdict(int)
    for e in entries:
        d[e.module] += e.size
    return d


def _signed(n: int) -> str:
    if n > 0:
        return f"+{human(n)}"
    if n < 0:
        return f"-{human(-n)}"
    return "0"


def diff_report(old: Result, new: Result, top: int = 12,
                old_name: str = "旧", new_name: str = "新") -> str:
    out: list[str] = []
    w = out.append

    o_all, n_all = old.total, new.total
    d_all = n_all - o_all
    pct = (d_all / o_all * 100) if o_all else 0.0

    w("")
    w(f"  旧  {old_name:<28}{human(o_all):>10}")
    w(f"  新  {new_name:<28}{human(n_all):>10}")
    w(f"  变化{'':<24}{_signed(d_all):>10}   ({pct:+.1f}%)")
    w("")

    for k in ("flash", "ram"):
        o = sum(e.size for e in old.entries if e.kind == k)
        n = sum(e.size for e in new.entries if e.kind == k)
        if not o and not n:
            continue
        d = n - o
        p = (d / o * 100) if o else 0.0
        w(f"  {k.upper():<6}{human(o):>10}  →  {human(n):<10}{_signed(d):>10}  ({p:+.1f}%)")
    w("")

    om, nm = _agg_mod(old.entries), _agg_mod(new.entries)
    added = {m: nm[m] for m in nm if m not in om}
    removed = {m: om[m] for m in om if m not in nm}
    if added:
        w(f"  新增模块 ({len(added)})")
        for m, s in sorted(added.items(), key=lambda kv: -kv[1])[:top]:
            w(f"    +{human(s):>9}  {m}")
        w("")
    if removed:
        w(f"  消失模块 ({len(removed)})")
        for m, s in sorted(removed.items(), key=lambda kv: -kv[1])[:top]:
            w(f"    -{human(s):>9}  {m}")
        w("")

    oa, na = _agg(old.entries), _agg(new.entries)
    deltas = []
    for key in set(oa) | set(na):
        d = na.get(key, 0) - oa.get(key, 0)
        if d:
            deltas.append((d, key))
    grow = sorted([x for x in deltas if x[0] > 0], key=lambda x: -x[0])[:top]
    shrink = sorted([x for x in deltas if x[0] < 0], key=lambda x: x[0])[:top]

    if grow:
        w("  变大的符号")
        for d, (mod, sym) in grow:
            w(f"    {_signed(d):>10}  {pad(sym[:30], 30)}  {mod}")
        w("")
    if shrink:
        w("  变小的符号")
        for d, (mod, sym) in shrink:
            w(f"    {_signed(d):>10}  {pad(sym[:30], 30)}  {mod}")
        w("")

    if not added and not removed and not deltas:
        w("  两份 map 完全一致。")
        w("")

    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mapviewer",
        description="读懂 map 文件: 谁占了你的 Flash / RAM",
    )
    p.add_argument("map", type=Path, help="map 文件路径")
    p.add_argument("-n", "--top", type=int, default=20, help="显示前 N 条 (默认 20)")
    p.add_argument(
        "-k", "--kind", choices=["all", "flash", "ram"], default="all",
        help="只看 flash 或 ram",
    )
    p.add_argument(
        "-b", "--by", choices=["symbol", "module"], default="symbol",
        help="按符号还是按模块聚合",
    )
    p.add_argument("--html", type=Path, help="同时导出一份 HTML 报告")
    p.add_argument("--with-meta", action="store_true",
                   help="把 .debug_* / .comment 等调试信息也算进来(默认不算, 它们不占 Flash)")
    p.add_argument("--diff", type=Path, metavar="OLD_MAP",
                   help="和另一份 map 对比(当前文件当作新版本)")
    p.add_argument("--discarded", action="store_true",
                   help="看被 --gc-sections 丢掉的段, 以及哪些模块整个没用上")
    args = p.parse_args(argv)

    # 兜底: 控制台编码怪异时也不让程序崩在打印上
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    if not args.map.exists():
        print(f"找不到文件: {args.map}", file=sys.stderr)
        return 2

    res = parse(args.map)
    if not res.entries:
        print("解析完成, 但没有条目。可能这个 map 是 --gc-sections 之前的, 或者格式需要适配。",
              file=sys.stderr)
        return 1

    if not args.with_meta:
        res.entries = [e for e in res.entries if e.kind != "meta"]

    if args.discarded:
        print(discarded_report(res, args.top))
        return 0

    if args.diff:
        if not args.diff.exists():
            print(f"找不到文件: {args.diff}", file=sys.stderr)
            return 2
        old = parse(args.diff)
        if not args.with_meta:
            old.entries = [e for e in old.entries if e.kind != "meta"]
        def label(path: Path) -> str:
            n = path.parent.name
            return n if n and n not in ("", ".") else path.stem
        print(diff_report(old, res, args.top, label(args.diff), label(args.map)))
        return 0

    print(report(res, args.top, args.by, args.kind))

    if args.html:
        args.html.write_text(to_html(res, args.top, args.map.stem), encoding="utf-8")
        print(f"  HTML 报告已写入: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
