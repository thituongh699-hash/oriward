"""Render README artwork. Optional tooling: Pillow and Latin/CJK fonts.

No project state is read. Font paths can be overridden for non-Windows hosts.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
INK, PAPER, MINT = "#132237", "#F5F3EC", "#CBF28A"
TEAL, GRAY, LINE = "#427C78", "#64716D", "#D4DAD0"
SCALE = 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, default=Path.home() / ".agents/skills/canvas-design/canvas-fonts")
    parser.add_argument("--cjk-font", type=Path, default=Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc")
    parser.add_argument("--cjk-bold", type=Path, default=Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyhbd.ttc")
    args = parser.parse_args()
    fonts = {"en": args.font_dir / "InstrumentSans-Regular.ttf",
             "bold": args.font_dir / "InstrumentSans-Bold.ttf",
             "serif": args.font_dir / "InstrumentSerif-Italic.ttf",
             "mono": args.font_dir / "GeistMono-Regular.ttf",
             "cn": args.cjk_font, "cnb": args.cjk_bold}
    for path in fonts.values():
        if not path.is_file():
            parser.error(f"Font not found: {path}. Use --font-dir / --cjk-font / --cjk-bold.")
    output = ROOT / "docs/assets"
    output.mkdir(parents=True, exist_ok=True)
    cache = {}

    class Canvas:
        def __init__(self, w, h, bg):
            self.w, self.h = w, h
            self.im = Image.new("RGB", (w*SCALE, h*SCALE), bg)
            self.d = ImageDraw.Draw(self.im)

        def text(self, x, y, s, size=24, fill=INK, font="cn", anchor=None):
            key = (font, size)
            if key not in cache:
                cache[key] = ImageFont.truetype(str(fonts[font]), size*SCALE)
            f = cache[key]
            box = self.d.textbbox((x*SCALE, y*SCALE), s, font=f, anchor=anchor)
            if min(box[:2]) < 0 or box[2] > self.w*SCALE or box[3] > self.h*SCALE:
                raise ValueError(f"Text outside canvas: {s!r}, {box}")
            self.d.text((x*SCALE, y*SCALE), s, font=f, fill=fill, anchor=anchor)

        def line(self, points, fill=LINE, width=2):
            self.d.line([(round(x*SCALE), round(y*SCALE)) for x, y in points], fill=fill,
                        width=width*SCALE, joint="curve")

        def rect(self, box, fill, radius=0, outline=None):
            self.d.rounded_rectangle(tuple(round(v*SCALE) for v in box), radius=radius*SCALE,
                                     fill=fill, outline=outline, width=SCALE)

        def circle(self, x, y, r, fill=None, outline=None, width=1):
            self.d.ellipse(tuple(round(v*SCALE) for v in (x-r, y-r, x+r, y+r)),
                           fill=fill, outline=outline, width=width*SCALE)

        def arrow(self, points, fill=TEAL, width=2):
            self.line(points, fill, width)
            (x0, y0), (x, y) = points[-2:]
            angle = math.atan2(y-y0, x-x0)
            a, b = angle+2.65, angle-2.65
            self.line([(x+12*math.cos(a), y+12*math.sin(a)), (x, y),
                       (x+12*math.cos(b), y+12*math.sin(b))], fill, width)

        def save(self, name):
            self.im.resize((self.w, self.h), Image.Resampling.LANCZOS).save(output/name, optimize=True)
            print(f"{name}: {self.w}x{self.h}")

    c = Canvas(1600, 900, INK)
    c.text(76, 45, "CAREER TWIN / AN OPEN-SOURCE WORKBENCH", 17, MINT, "mono")
    c.text(74, 115, "Oriward", 144, PAPER, "bold")
    c.text(81, 273, "原向", 34, MINT, "cnb")
    c.text(78, 369, "从「我能做什么」", 53, PAPER, "cnb")
    c.text(78, 447, "到「下一步怎么走」", 53, PAPER, "cnb")
    c.text(81, 560, "记得来路，走向可能。", 27, "#B9C6C6")
    c.text(81, 634, "FOR STUDENTS & RECENT GRADUATES", 16, "#8EAAA8", "mono")
    for x in range(939, 1501, 35):
        for y in range(125, 650, 35):
            c.circle(x, y, 1.2, "#304253")
    for r in (88, 151, 221):
        c.circle(1214, 370, r, outline="#3B535D")
    c.line([(920, 585), (1005, 500), (1066, 500), (1133, 430), (1214, 370), (1327, 306), (1420, 171)], MINT, 4)
    c.line([(1214, 370), (1341, 425), (1474, 425)], "#688F8D", 2)
    c.line([(1005, 500), (1005, 343), (1084, 238)], "#688F8D", 2)
    for x, y in ((920, 585), (1005, 500), (1084, 238), (1327, 306), (1474, 425)):
        c.circle(x, y, 7, INK, MINT, 2)
    c.circle(1420, 171, 10, MINT)
    c.circle(1214, 370, 48, MINT)
    c.text(1214, 370, "YOU", 24, INK, "bold", "mm")
    c.text(1302, 566, "evidence", 19, "#A5BDBC", "serif")
    c.text(1330, 597, "into possibility", 27, PAPER, "serif")
    c.line([(78, 743), (1522, 743)], "#3A4C59", 1)
    for i, label in enumerate(("认识自己", "探索方向", "推进行动", "反馈修正")):
        x = 81+i*367
        c.text(x, 790, f"0{i+1}", 18, MINT, "mono")
        c.text(x+54, 781, label, 26, PAPER)
    c.save("oriward-cover.png")

    a = Canvas(1600, 1080, PAPER)
    a.text(72, 44, "THE ARCHITECTURE", 17, TEAL, "mono")
    a.text(70, 91, "一个持续的理解，八种具体的行动。", 43, INK, "cnb")
    a.rect((72, 190, 1528, 290), INK, 15)
    a.text(102, 211, "你的 Agent", 29, MINT, "cnb")
    a.text(340, 224, "理解与判断 · 按需加载 Skills · 通过 CLI 读写状态", 25, PAPER)
    a.arrow([(800, 290), (800, 338)])
    a.rect((170, 340, 1430, 592), "#FFFFFF", 18, LINE)
    a.text(205, 362, "CAREER TWIN CORE", 27, INK, "bold")
    a.text(1040, 367, "Python CLI + SQLite", 20, TEAL, "mono")
    for i, (title, detail, update) in enumerate((
        ("长期 · 我是谁", "经历 / 能力 / 价值观 / 约束", "访谈、证据与用户确认"),
        ("中期 · 我想成为什么", "方向假设 / 目标 / 差距 / 规划", "机会、探索与目标变化"),
        ("短期 · 我正在做什么", "岗位 / 申请 / 面试 / 下一步", "真实操作与结果反馈"))):
        x = 205+406*i
        if i:
            a.line([(x-21, 437), (x-21, 552)], LINE, 1)
        a.text(x, 435, title, 25, INK, "cnb")
        a.text(x, 483, detail, 21, GRAY)
        a.text(x, 527, update, 20, TEAL)
    a.arrow([(800, 593), (800, 671)])
    a.rect((626, 614, 975, 650), PAPER)
    a.text(800, 632, "读取相关状态与依据", 20, TEAL, anchor="mm")
    a.rect((170, 676, 1430, 918), INK, 18)
    a.text(205, 697, "EXECUTION SKILLS", 21, MINT, "mono")
    labels = [("经历发现", "career-discovery"), ("方向探索", "career-mapping"),
              ("岗位搜索", "job-search"), ("岗位分析", "job-analysis"),
              ("简历构建", "resume-builder"), ("申请协助", "application-assistant"),
              ("学习规划", "learning-planner"), ("面试辅导", "interview-coach")]
    for i, (cn, en) in enumerate(labels):
        x, y = 205+(i % 4)*307, 750+(i//4)*76
        a.text(x, y, cn, 24, PAPER, "cnb")
        a.text(x, y+36, en, 14, "#9EB9B8", "mono")
    a.arrow([(1430, 797), (1498, 797), (1498, 454), (1431, 454)], TEAL, 3)
    a.text(800, 979, "操作结果 → 情境反馈 → 核实与确认 → 更新状态 / 重评建议", 25, INK, anchor="mm")
    a.text(800, 1032, "8 个职业 Skills 写回 Core；document-export 仅作格式转换。无内置模型服务或后台进程。", 19, GRAY, anchor="mm")
    a.save("oriward-architecture.png")

    p = Canvas(1200, 1600, PAPER)
    p.rect((0, 0, 1200, 615), INK)
    p.text(74, 52, "FOR THE NEXT CHAPTER", 18, MINT, "mono")
    p.text(68, 107, "Oriward", 150, PAPER, "bold")
    p.text(78, 281, "原向", 43, MINT, "cnb")
    p.text(77, 392, "记得来路，", 48, PAPER, "cnb")
    p.text(77, 465, "走向可能。", 48, PAPER, "cnb")
    p.text(80, 657, "FOUR QUESTIONS. ONE CONTINUOUS UNDERSTANDING.", 17, TEAL, "mono")
    questions = [("01", "Who am I?", "我是谁，经历过什么、看重什么？"),
                 ("02", "Who could I become?", "我的能力，还可能走向哪里？"),
                 ("03", "Where am I now?", "正在推进什么，又卡在哪里？"),
                 ("04", "What should I do next?", "结合真实目标，下一步值得做什么？")]
    for i, (number, en, cn) in enumerate(questions):
        y = 724+i*136
        p.circle(102, y+32, 22, MINT)
        p.text(102, y+32, number, 17, INK, "mono", "mm")
        if i < 3:
            p.line([(102, y+58), (102, y+111)], LINE, 2)
        p.text(155, y-2, en, 35, INK, "bold")
        p.text(157, y+56, cn, 25, GRAY)
        p.line([(155, y+111), (1120, y+111)], LINE, 1)
    p.rect((76, 1289, 1124, 1473), MINT, 15)
    p.text(106, 1310, "+  Why do you think so?", 43, INK, "serif")
    p.text(109, 1382, "为什么这样认为？依据是什么，又因何改变？", 27, INK, "cnb")
    p.text(80, 1514, "CAREER TWIN CORE + SKILLS", 18, TEAL, "mono")
    p.text(1120, 1526, "面向在校生与应届生 · 本地求职成长工作台", 20, GRAY, anchor="ra")
    p.save("oriward-poster.png")


if __name__ == "__main__":
    main()
