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

    @property
    def symbol(self) -> str:
        """.text.main -> main ; .bss -> .bss"""
        s = self.section
        if s.startswith(".") and s.count(".") >= 2:
            return s.split(".", 2)[2]
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
    memories: list[Memory] = field(default_factory=list)
    fmt: str = ""

    @property
    def total(self) -> int:
        return sum(e.size for e in self.entries)


# --------------------------------------------------------------------------
# 段归类: 一个段到底占 Flash 还是 RAM
# --------------------------------------------------------------------------

FLASH_PREFIX = (
    ".text", ".rodata", ".isr_vector", ".init", ".fini",
    ".ARM", ".eh_frame", ".glue", ".vectors", ".data.rel.ro",
)
RAM_PREFIX = (".bss", ".data", ".noinit", ".heap", ".stack", ".ccmram", "COMMON")


def kind_of(section: str) -> str:
    s = section
    if s.startswith("COMMON"):
        return "ram"
    for p in FLASH_PREFIX:
        if s.startswith(p):
            # .data 在 Flash 里也有一份初值, 但可写数据主要在 RAM, 这里统一归 RAM
            return "flash"
    for p in RAM_PREFIX:
        if s.startswith(p):
            return "ram"
    return "other"


# --------------------------------------------------------------------------
# 解析: GCC
# --------------------------------------------------------------------------

RE_GCC_MEM = re.compile(r"^(\S+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)")
RE_GCC_IN = re.compile(r"^\s(\S+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+(\S.*)$")
RE_GCC_OBJ = re.compile(r"(\.o|\.a\(|\.obj|\.lib\()")


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

    # 2) 输入段
    in_map = False
    for l in lines:
        if l.startswith("Linker script and memory map"):
            in_map = True
            continue
        if not in_map:
            continue
        m = RE_GCC_IN.match(l)
        if not m:
            continue
        section, addr, size, rest = m.group(1), int(m.group(2), 16), int(m.group(3), 16), m.group(4)
        rest = rest.strip()
        if not RE_GCC_OBJ.search(rest):
            continue  # 这一行是符号赋值或链接脚本指令, 不是目标文件
        if section in ("*fill*",):
            continue
        res.entries.append(Entry(section, addr, size, rest.split()[0]))

    # 3) 合并同名同源, 去掉 0 字节
    res.entries = _merge([e for e in res.entries if e.size > 0])
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
            if cap and not cap >= 0xFFFFFFFF:
                res.memories.append(Memory(name, 0, cap))
    if got:
        res.entries = _merge([e for e in res.entries if e.size > 0])
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
    return "█" * filled + "░" * (width - filled)


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
        entries = [e for e in entries if kind_of(e.section) == kind]

    if not entries:
        return "没有解析到任何条目, 检查一下 map 文件是不是空的, 或者段名规则要不要补充。"

    total = sum(e.size for e in entries)

    w("")
    w(f"  格式        {res.fmt}")
    w(f"  条目        {len(entries)} 条")
    w(f"  合计        {human(total)}")
    w("")

    # 空间占用条
    for k in ("flash", "ram"):
        sub = [e for e in entries if kind_of(e.section) == k]
        if not sub:
            continue
        used = sum(e.size for e in sub)
        mem = pick_memory(res, k)
        cap = mem.length if mem else None
        if cap:
            r = used / cap
            w(f"  {k.upper():<6}{human(used):>10} / {human(cap):<10} {r * 100:5.1f}%  {bar(r, 30)}")
        else:
            w(f"  {k.upper():<6}{human(used):>10}  (map 里没有声明容量)")

    # 按模块聚合
    if by == "module":
        agg: dict[str, int] = defaultdict(int)
        for e in entries:
            agg[e.module] += e.size
        rows = sorted(agg.items(), key=lambda kv: -kv[1])[:top]
        w("")
        w("  " + pad("#", 3, "right") + "  " + pad("大小", 10, "right")
          + "  " + pad("占比", 6, "right") + "  模块")
        w("  " + "-" * 64)
        for i, (name, size) in enumerate(rows, 1):
            w("  " + pad(str(i), 3, "right") + "  " + pad(human(size), 10, "right")
              + "  " + pad(f"{size / total * 100:.1f}%", 6, "right") + "  " + name)
        return "\n".join(out) + "\n"

    # 按符号排序
    rows = sorted(entries, key=lambda e: -e.size)[:top]
    w("")
    w("  " + pad("#", 3, "right") + "  " + pad("大小", 10, "right")
      + "  " + pad("占比", 6, "right") + "  " + pad("符号", 30) + "  来源")
    w("  " + "-" * 90)
    for i, e in enumerate(rows, 1):
        src = e.module + ("  [lib]" if e.is_lib else "")
        w("  " + pad(str(i), 3, "right") + "  " + pad(human(e.size), 10, "right")
          + "  " + pad(f"{e.size / total * 100:.1f}%", 6, "right")
          + "  " + pad(e.symbol[:30], 30) + "  " + src)

    # 自己写的 vs 库
    lib = sum(e.size for e in entries if e.is_lib)
    mine = total - lib
    w("")
    w("  谁在占地方:")
    w(f"    我的代码  {human(mine):>10}  {mine / total * 100:5.1f}%  {bar(mine / total)}")
    w(f"    静态库    {human(lib):>10}  {lib / total * 100:5.1f}%  {bar(lib / total)}")
    if lib > mine:
        w("")
        w("  ⚠ 库比你自己的代码占得多。这是嵌入式的常态, 但也是最大的优化空间:")
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
        sub = [e for e in res.entries if kind_of(e.section) == k]
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
    args = p.parse_args(argv)

    if not args.map.exists():
        print(f"找不到文件: {args.map}", file=sys.stderr)
        return 2

    res = parse(args.map)
    if not res.entries:
        print("解析完成, 但没有条目。可能这个 map 是 --gc-sections 之前的, 或者格式需要适配。",
              file=sys.stderr)
        return 1

    print(report(res, args.top, args.by, args.kind))

    if args.html:
        args.html.write_text(to_html(res, args.top, args.map.stem), encoding="utf-8")
        print(f"  HTML 报告已写入: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
