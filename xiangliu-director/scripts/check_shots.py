# -*- coding: utf-8 -*-
"""
六锁自检脚本：检查提示词成品的镜头切换
用法：python check_shots.py 提示词文件.txt
检查六条（与手册规则一致）：
1. 写法：景别槽必须能拆出"主体+景别词"；机位槽必须含"机位"两字
2. 变化：相邻两镜的主体、机位、景别，至少两项不同
3. 连续：禁止连续三个或三个以上镜头为同一主体；
   同主体连续镜头内，机位禁止来回切（第1词＝第3词）
4. 时长：单镜超过4秒报警；相邻镜头时间不衔接（重叠或空档）报警；
   段落总时长超过30秒报警
5. 禁词：镜头正文出现硬禁项词（死死、紧绷、面部变色、眼神发亮、网文套式类）逐镜报警
6. 骨架：镜2起正文必须以"承接"开头（每段首镜省略）；每镜正文必须含"落幅"
运镜槽不查词库：有没有入参照表的高级运镜都放行，只禁止空槽。
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 景别词库（长词在前，匹配优先："大全景"先于"全景"）
JINGBIE = ["大全景", "全景", "中近景", "中景", "近景", "特写"]

# 硬禁项词表（与情绪演绎规则.md硬禁项、05-文风/文风规则.md套式禁笔同源；子串匹配）
BANNED = [
    # 眼睛变色类
    "眼眶泛红", "眼睛发红", "眼眶红",
    # 面部变色类
    "泛白", "煞白", "铁青", "惨白",
    # 面部硬度类
    "紧绷", "绷紧", "绷着", "僵硬", "僵直", "发硬",
    # "死死"类
    "死死",
    # 眼神特效类
    "眼神发亮", "眼里闪过", "眼中闪过", "发亮",
    # 定格类
    "僵在原地", "钉在原地", "石化",
    # 节奏套路类
    "一字一顿", "一字一句",
    # 脸谱类
    "冷脸", "黑着脸", "黑脸",
    # 抽气类
    "倒吸一口凉气", "倒吸凉气", "抽气", "缩气",
    # "动词＋死"程度类
    "顶死", "瞪死", "咬死", "按死",
    # 网文套式类（与 05-文风/文风规则.md 套式禁笔同源）
    "拧起眉头", "拧眉", "勾起嘴角", "嘴角勾", "勾唇",
    "邪魅", "眸光", "眼底闪过", "瞳孔",
    "心如刀绞", "怒火中烧",
    "眼睛一亮", "眼里的光暗", "眼神里的光暗", "拢起手",
    "眉心拢", "脸变红", "脸一黑", "扯出个笑",
]

HEAD = re.compile(r"【镜头(\d+)｜([^\n｜]+)｜([^\n｜]+)｜([^\n｜]+)｜([^\n｜]+)】")

TIME = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


def parse_time(slot):
    """'0-3s' -> (0.0, 3.0)；'6-10s' -> (6.0, 10.0)；解析失败 -> (None, None)"""
    m = TIME.search(slot)
    if not m:
        return None, None
    return float(m.group(1)), float(m.group(2))


def split_subject_jingbie(slot):
    """'男主近景' -> ('男主', '近景')；'海岸线大全景' -> ('海岸线', '大全景')"""
    slot = slot.strip()
    for jb in JINGBIE:
        if slot.endswith(jb):
            subject = slot[: -len(jb)].strip()
            if subject:
                return subject, jb
            return None, jb  # 有景别词没有主体："大全景"
    return None, None


def normalize_cam(slot):
    """'女主左肩后机位' -> '女主左肩后'；'正面机位+低角度' -> '正面+低角度'"""
    return slot.replace("机位", "").strip()


def parse(text):
    """解析全部【镜头N】行，返回镜头列表（含每镜正文，供禁词扫描）"""
    shots = []
    matches = list(HEAD.finditer(text))
    for i, m in enumerate(matches):
        subject, jb = split_subject_jingbie(m.group(3))
        t_start, t_end = parse_time(m.group(2))
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = re.sub(r"^[\s：:]+", "", text[m.end() : body_end])  # 去掉"】："的冒号
        shots.append(
            {
                "num": int(m.group(1)),
                "time_raw": m.group(2).strip(),
                "start": t_start,
                "end": t_end,
                "slot_raw": m.group(3).strip(),
                "subject": subject,
                "jingbie": jb,
                "cam_raw": m.group(4).strip(),
                "cam": normalize_cam(m.group(4)),
                "body": body,
            }
        )
    return shots


def check(text):
    """六锁检查，返回 (镜头列表, 问题列表)；问题列表为空即全过"""
    shots = parse(text)
    problems = []

    # 锁一：写法
    for s in shots:
        if s["subject"] is None:
            problems.append(
                f"镜{s['num']}：景别槽“{s['slot_raw']}”拆不出主体＋景别词，"
                f"景别词库：大全景/全景/中近景/中景/近景/特写"
            )
        if "机位" not in s["cam_raw"]:
            problems.append(f"镜{s['num']}：机位槽“{s['cam_raw']}”不含“机位”两字")

    # 锁二：相邻两镜至少两项变化
    for a, b in zip(shots, shots[1:]):
        diff = sum(
            [
                a["subject"] != b["subject"],
                a["cam"] != b["cam"],
                a["jingbie"] != b["jingbie"],
            ]
        )
        if diff < 2:
            problems.append(
                f"镜{a['num']}→镜{b['num']}：主体/机位/景别只变了{diff}样，必须至少两样"
                f"（{a['subject']}·{a['cam']}·{a['jingbie']} → "
                f"{b['subject']}·{b['cam']}·{b['jingbie']}）"
            )

    # 锁三：同主体连续计数 ＋ 机位来回切
    runs = []
    cur = [shots[0]]
    for s in shots[1:]:
        if s["subject"] is not None and s["subject"] == cur[-1]["subject"]:
            cur.append(s)
        else:
            runs.append(cur)
            cur = [s]
    runs.append(cur)

    for run in runs:
        if run[0]["subject"] is None:
            continue
        if len(run) >= 3:
            nums = "、".join(f"镜{s['num']}" for s in run)
            problems.append(
                f"{nums}：同一主体“{run[0]['subject']}”连拍{len(run)}镜，"
                f"禁止连续三个或三个以上镜头为同一主体"
            )
        cams = [s["cam"] for s in run]
        seen_aba = False
        for i in range(2, len(cams)):
            if cams[i] == cams[i - 2] and cams[i] != cams[i - 1] and not seen_aba:
                problems.append(
                    f"镜{run[i - 2]['num']}→镜{run[i]['num']}："
                    f"同主体机位来回切（{cams[i - 2]}→{cams[i - 1]}→{cams[i]}）"
                )
                seen_aba = True

    # 锁四：时长与时间轴衔接
    prev_end = None
    for s in shots:
        if s["start"] is None:
            problems.append(f"镜{s['num']}：时间槽“{s['time_raw']}”解析不出时长（格式应为 0-3s）")
            continue
        dur = s["end"] - s["start"]
        if dur > 4 + 1e-9:
            problems.append(f"镜{s['num']}：时长{dur:g}秒，超过4秒上限")
        if prev_end is not None and abs(s["start"] - prev_end) > 1e-9:
            gap = s["start"] - prev_end
            kind = "重叠" if gap < 0 else "空档"
            problems.append(
                f"镜{s['num']}：开始{s['start']:g}s与上一镜结束{prev_end:g}s不衔接（{kind}{abs(gap):g}秒）"
            )
        prev_end = s["end"]

    # 段落总时长：最后一镜的结束时间不得超过30秒
    if shots:
        last = shots[-1]
        if last["end"] is not None and last["end"] > 30 + 1e-9:
            problems.append(
                f"段落总时长{last['end']:g}秒，超过30秒上限——"
                f"段由旁白行累计时长切，30s为上限非配额，超出的旁白划归下一段"
            )

    # 锁五：禁词（逐镜正文扫描硬禁项；长词命中后不再报其包含的短词）
    for s in shots:
        hits = []
        for w in sorted(BANNED, key=len, reverse=True):
            if w in s["body"] and not any(w in h for h in hits):
                hits.append(w)
        if hits:
            problems.append(f"镜{s['num']}：正文出现禁词“{'、'.join(hits)}”")

    # 锁六：骨架（镜2起正文必须以"承接"开头；每镜正文必须含"落幅"）
    for s in shots:
        body = s["body"].strip()
        if s["num"] >= 2 and not body.startswith("承接"):
            problems.append(
                f"镜{s['num']}：正文开头没有承接——镜2起必须以“承接上一镜”开头"
                f"（每段首镜省略）"
            )
        if "落幅" not in body:
            problems.append(f"镜{s['num']}：正文没有落幅收尾")

    return shots, problems


def format_table(shots):
    """逐镜比对表"""
    lines = ["=" * 72]
    lines.append(f"{'镜':<4}{'时间':<10}{'主体':<12}{'机位':<16}{'景别':<8}与上镜变化")
    lines.append("-" * 72)
    prev = None
    for s in shots:
        if prev is None:
            change = "—（首镜）"
        else:
            n = sum(
                [
                    prev["subject"] != s["subject"],
                    prev["cam"] != s["cam"],
                    prev["jingbie"] != s["jingbie"],
                ]
            )
            change = f"变了{n}样" + ("" if n >= 2 else "  ← 不合格")
        subj = s["subject"] if s["subject"] is not None else f"??({s['slot_raw']})"
        jb = s["jingbie"] if s["jingbie"] is not None else "??"
        tinfo = f"{s['start']:g}-{s['end']:g}s" if s["start"] is not None else s["time_raw"]
        lines.append(f"{s['num']:<4}{tinfo:<10}{subj:<12}{s['cam']:<16}{jb:<8}{change}")
        prev = s
    lines.append("=" * 72)
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("用法：python check_shots.py 提示词文件.txt")
        return
    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    shots, problems = check(text)
    if not shots:
        print("没有解析到【镜头N】行，请检查文件格式。")
        return

    print(format_table(shots))
    if problems:
        print(f"发现 {len(problems)} 个问题：")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
        print("结论：不过检，改镜后重新跑。")
    else:
        print("结论：六锁全过，可以组装。")


if __name__ == "__main__":
    main()
