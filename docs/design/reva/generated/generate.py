#!/usr/bin/env python3
"""复元 Reva — data-driven design稿 generator.

Renders the Reva design-system screens (今天 / 数据 / 我的) into static HTML
populated with a REAL user's data (user_id=3, "Suntice"), pulled from production.
This is the "real data → 反向同步给设计稿" loop: the design稿 mirror the live
screens with real content. Re-run with a fresh _data-user3.json to refresh.

Usage: python3 generate.py   (reads ./_data-user3.json, writes ./*.html)
"""
import json, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = json.load(open(os.path.join(HERE, "_data-user3.json"), encoding="utf-8"))
TODAY = datetime.date(2026, 6, 3)  # snapshot date (matches the data pull)

prof = (DATA["profile"] or [{}])[0]
user = (DATA["user"] or [{}])[0]
garmin = DATA["garmin"]  # desc by date
latest = garmin[0] if garmin else {}
exam = (DATA["exam"] or [{}])[0]
items = DATA["exam_items"]
plan = (DATA["plan"] or [{}])[0]
plan_first = (DATA["plan_first_date"] or [{}])[0].get("d")

def age(bd):
    if not bd: return None
    y = datetime.date.fromisoformat(bd)
    return TODAY.year - y.year - ((TODAY.month, TODAY.day) < (y.month, y.day))

def sleep_fmt(mins):
    # 时长统一规范: 十进制小时 + 小时 (一位小数), 不用 "7h10"/"7:10" 这种像时间戳的写法
    if mins is None: return "—"
    return f"{mins/60:.1f} 小时"

name = user.get("username", "我")
gender = {"male": "男", "female": "女"}.get(prof.get("gender"), "")
A = age(prof.get("birth_date"))
meta = " · ".join([x for x in [gender, f"{A} 岁" if A else None, prof.get("city"), "心代谢管理中"] if x])

readiness = latest.get("body_battery_current") or latest.get("sleep_score")
rtitle = ("数据接入中" if readiness is None else
          "已就绪 · 适合中等强度" if readiness >= 80 else
          "基本就绪 · 适度活动" if readiness >= 60 else "偏低 · 注意恢复")
rnote_bits = []
if latest.get("resting_heart_rate") is not None: rnote_bits.append(f"静息心率 {latest['resting_heart_rate']} bpm")
if latest.get("total_sleep_duration") is not None: rnote_bits.append(f"睡眠 {sleep_fmt(latest['total_sleep_duration'])}")
rnote = "，".join(rnote_bits) or "已接入手环数据"

# RHR sparkline (chronological, last 7)
rhr = [r["resting_heart_rate"] for r in reversed(garmin[:7]) if r.get("resting_heart_rate") is not None]

# day in 90-day window
day = None
if plan_first:
    day = max(1, min(90, (TODAY - datetime.date.fromisoformat(plan_first)).days + 1))

# abnormal lab items
ABN = {"high": ("risk", "偏高 · 注意"), "low": ("caution", "偏低 · 注意"), "abnormal": ("caution", "异常 · 注意")}
abn = [(it, *ABN[it["is_abnormal"]]) for it in items if it.get("is_abnormal") in ABN]

# plan actions
DOMAIN_ICON = {"measurement": "gauge", "nutrition": "utensils", "movement": "footprints",
               "sleep": "moon", "intervention": "pill", "doctor": "calendar-check"}
actions = plan.get("actions") or []

def esc(s): return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def sparkline_svg(points, w=300, h=44):
    if len(points) < 2: return ""
    mn, mx = min(points), max(points)
    xs = [i / (len(points) - 1) * w for i in range(len(points))]
    ys = [h - 2 - (v - mn) / ((mx - mn) or 1) * (h - 4) for v in points]
    d = " ".join(f"{'L' if i else 'M'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    return (f'<svg width="100%" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" style="display:block">'
            f'<path d="{d} L{w},{h} L0,{h} Z" fill="var(--green-500)" opacity="0.08"/>'
            f'<path d="{d}" fill="none" stroke="var(--green-500)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3.2" fill="var(--green-500)"/></svg>')

HEAD = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=390, initial-scale=1">
<title>复元 Reva · {title}（真实数据 · user_id=3）</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="../colors_and_type.css">
<script src="https://unpkg.com/lucide@latest"></script>
<style>
  * {{ box-sizing:border-box; margin:0; }} body {{ background:#cfcfca; font-family:var(--font-sans); display:flex; justify-content:center; padding:24px; }}
  .phone {{ width:390px; background:var(--paper); border-radius:34px; overflow:hidden; box-shadow:var(--shadow-lg); }}
  .src {{ font-family:var(--font-mono); font-size:10px; color:var(--ink3); text-align:center; padding:6px; background:var(--paper-2); }}
  .topbar {{ padding:20px 20px 14px; display:flex; align-items:flex-end; justify-content:space-between; border-bottom:1px solid var(--line); }}
  .topbar .sub {{ font-size:12px; font-weight:600; color:var(--ink-3); }} .topbar .ttl {{ font-size:21px; font-weight:800; letter-spacing:-.02em; color:var(--ink-1); }}
  .avatar {{ width:40px; height:40px; border-radius:50%; background:var(--green-50); color:var(--green-600); display:flex; align-items:center; justify-content:center; font-weight:700; }}
  .body {{ padding:16px; display:flex; flex-direction:column; gap:22px; }}
  .card {{ background:var(--surface); border:1px solid var(--line); border-radius:18px; box-shadow:var(--shadow-md); }}
  .card.p {{ padding:18px; }}
  .ov {{ font-weight:600; font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-3); padding:0 4px; margin-bottom:10px; display:flex; justify-content:space-between; }}
  .ov .act {{ color:var(--green-600); text-transform:none; letter-spacing:0; }}
  .hero {{ background:var(--focus-bg); border-radius:24px; padding:20px; display:flex; gap:18px; align-items:center; box-shadow:var(--shadow-focus); }}
  .ring {{ width:104px; height:104px; flex:none; position:relative; }} .ring .v {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-family:var(--font-mono); font-weight:500; font-size:36px; color:var(--focus-ink-1); }}
  .row {{ display:flex; align-items:center; gap:13px; padding:13px 16px; border-bottom:1px solid var(--line); }} .row:last-child {{ border-bottom:none; }}
  .rl {{ width:38px; height:38px; border-radius:11px; display:flex; align-items:center; justify-content:center; background:var(--paper-2); color:var(--ink-2); flex:none; }}
  .dot {{ width:9px; height:9px; border-radius:50%; flex:none; }}
  .val {{ font-family:var(--font-mono); font-weight:500; font-size:18px; }}
  .tiles {{ display:flex; gap:10px; }} .tile {{ flex:1; background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:13px 14px; box-shadow:var(--shadow-sm); }}
  .tile .l {{ display:flex; align-items:center; gap:7px; font-size:12px; font-weight:600; color:var(--ink-2); margin-bottom:9px; }}
  .tile .n {{ font-family:var(--font-mono); font-weight:500; font-size:22px; }}
  .chip {{ display:inline-flex; align-items:center; gap:6px; padding:4px 10px; border-radius:999px; font-weight:600; font-size:12px; }}
  .prog {{ height:8px; border-radius:99px; background:var(--paper-2); overflow:hidden; }} .prog>div {{ height:100%; border-radius:99px; background:var(--green-500); }}
  i[data-lucide] {{ width:1em; height:1em; }}
</style></head><body><div class="phone"><div class="src">复元 Reva · 真实数据设计稿 · user_id=3（Suntice）· 快照 {date}</div>"""

FOOT = '</div><script>lucide.createIcons();</script></body></html>'


def write(fn, title, inner):
    html = HEAD.format(title=title, date=TODAY.isoformat()) + inner + FOOT
    open(os.path.join(HERE, fn), "w", encoding="utf-8").write(html)
    print("wrote", fn)


def icon(n, **st):
    style = ";".join(f"{k.replace('_','-')}:{v}" for k, v in st.items())
    return f'<i data-lucide="{n}"{f" style=\"{style}\"" if style else ""}></i>'


# ── Today ──────────────────────────────────────────────────────────────────
ring_r = 47
ring_circ = 2 * 3.14159 * ring_r
ring_off = ring_circ * (1 - (readiness or 0) / 100)
ring = (f'<div class="ring"><svg width="104" height="104"><circle cx="52" cy="52" r="{ring_r}" fill="none" stroke="var(--focus-line)" stroke-width="10"/>'
        f'<circle cx="52" cy="52" r="{ring_r}" fill="none" stroke="var(--green-bright)" stroke-width="10" stroke-linecap="round" '
        f'stroke-dasharray="{ring_circ:.1f}" stroke-dashoffset="{ring_off:.1f}" transform="rotate(-90 52 52)"/></svg>'
        f'<div class="v">{readiness if readiness is not None else "—"}</div></div>')
plan_rows = ""
for a in actions[:5]:
    ic = DOMAIN_ICON.get(a.get("domain"), "sparkles")
    sub = a.get("why") or a.get("when") or ""
    plan_rows += (f'<div class="row"><div class="rl">{icon(ic, font_size="19px")}</div>'
                  f'<div style="flex:1"><div style="font-weight:600;font-size:15px;color:var(--ink-1)">{esc(a.get("title",""))}</div>'
                  f'<div style="font-size:12.5px;color:var(--ink-3)">{esc(sub)}</div></div></div>')
focus = abn[0] if abn else None
focus_html = ""
if focus:
    it, st, lbl = focus
    bg = "#FBE8E4" if st == "risk" else "#FBF1DD"; fg = "#D5503A" if st == "risk" else "#C98A1E"
    focus_html = (f'<div><div class="ov">本阶段重点</div><div class="card p"><div style="display:flex;align-items:center;gap:12px">'
                  f'<div style="width:44px;height:44px;border-radius:12px;background:{bg};color:{fg};display:flex;align-items:center;justify-content:center;flex:none">{icon("trending-down", font_size="22px")}</div>'
                  f'<div style="flex:1"><div style="font-weight:700;font-size:15.5px;color:var(--ink-1)">{esc(it["item_name"])}</div>'
                  f'<div style="font-size:13px;color:var(--ink-2);margin-top:2px">{lbl} · {esc(it.get("value_text") or it.get("value"))} {esc(it.get("unit") or "")}</div></div>'
                  f'{icon("chevron-right", font_size="20px", color="var(--ink-4)")}</div></div></div>')

steps = latest.get("steps"); bp = None
today_inner = f"""<div class="topbar"><div><div class="sub">{['凌晨好','早上好','中午好','下午好','晚上好'][3]} · {TODAY.month}月{TODAY.day}日</div><div class="ttl">{esc(name)}，今天</div></div><div class="avatar">{esc(name[:1])}</div></div>
<div class="body">
  <div class="hero">{ring}<div style="flex:1"><div style="font-family:var(--font-mono);font-size:11px;letter-spacing:.08em;color:var(--focus-ink-2)">TODAY · 恢复就绪度</div><div style="font-weight:700;font-size:18px;color:var(--green-bright);margin:4px 0 6px">{rtitle}</div><div style="font-size:13.5px;line-height:1.5;color:var(--focus-ink-2)">{esc(rnote)}</div></div></div>
  <div><div class="ov">今日计划<span class="act">{len(actions)} 项</span></div><div class="card">{plan_rows}<div style="padding:12px 16px;display:flex;align-items:center;gap:8px;color:var(--ink-3);font-size:12.5px">{icon("sparkles", color="var(--green-500)")} 计划每天根据你的数据自动调整</div></div></div>
  <div><div class="ov">今日数据</div><div class="tiles">
    <div class="tile"><div class="l">{icon("footprints")} 步数</div><div class="n" style="color:var(--info)">{f"{steps/1000:.1f}k" if steps else "—"}</div></div>
    <div class="tile"><div class="l">{icon("moon")} 睡眠</div><div class="n" style="color:{'var(--caution)' if (latest.get('total_sleep_duration') or 999)<420 else 'var(--normal)'}">{sleep_fmt(latest.get('total_sleep_duration'))}</div></div>
    <div class="tile"><div class="l">{icon("activity")} HRV</div><div class="n" style="color:var(--normal)">{latest.get('hrv') or '—'}<span style="font-size:11px;color:var(--ink-3)"> ms</span></div></div>
  </div></div>
  {focus_html}
</div>"""
write("today.html", "今天", today_inner)

# ── Data ───────────────────────────────────────────────────────────────────
lab_rows = ""
SEM = {"risk": "var(--risk)", "caution": "var(--caution)", "normal": "var(--normal)"}
if abn:
    for it, st, lbl in abn:
        c = SEM[st]
        lab_rows += (f'<div class="row"><div class="dot" style="background:{c}"></div>'
                     f'<div style="flex:1"><div style="font-weight:600;font-size:15px;color:var(--ink-1)">{esc(it["item_name"])}</div>'
                     f'<div style="font-size:12px;font-weight:600;color:{c}">{lbl}</div></div>'
                     f'<div class="val" style="color:{c}">{esc(it.get("value_text") or it.get("value"))}<span style="font-size:11px;color:var(--ink-3)"> {esc(it.get("unit") or "")}</span></div></div>')
else:
    lab_rows = '<div style="padding:14px 16px;font-size:13.5px;color:var(--ink-3)">本次体检未见异常项。</div>'
spark = sparkline_svg(rhr) or '<div style="font-size:12.5px;color:var(--ink-3)">数据积累中</div>'
data_inner = f"""<div class="topbar"><div><div class="sub">体检 · {exam.get('exam_date','')}</div><div class="ttl">你的数据</div></div></div>
<div class="body">
  <div class="card p"><div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:7px"><span style="font-size:13px;font-weight:600;color:var(--ink-2)">90 天主动管理</span><span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-1)">第 {day or '—'} / 90 天</span></div><div class="prog"><div style="width:{round((day or 0)/90*100)}%"></div></div></div>
  <div><div class="ov">体检异常项<span class="act">{len(abn)} 项异常</span></div><div class="card">{lab_rows}</div></div>
  <div><div class="ov">手环数据<span class="act">近 7 天</span></div><div class="card p"><div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px"><span style="font-weight:600;font-size:14px;color:var(--ink-1)">静息心率</span><span class="val" style="font-size:20px;color:var(--normal)">{latest.get('resting_heart_rate') or '—'} <span style="font-size:11px;color:var(--ink-3)">bpm</span></span></div>{spark}<div style="font-size:12.5px;color:var(--ink-3);margin-top:4px">最近 7 天趋势</div></div>
  <div class="tiles" style="margin-top:10px">
    <div class="tile"><div class="l">{icon("moon")} 睡眠</div><div class="n" style="color:{'var(--caution)' if (latest.get('total_sleep_duration') or 999)<420 else 'var(--normal)'}">{sleep_fmt(latest.get('total_sleep_duration'))}</div></div>
    <div class="tile"><div class="l">{icon("activity")} HRV</div><div class="n" style="color:var(--normal)">{latest.get('hrv') or '—'}<span style="font-size:11px;color:var(--ink-3)"> ms</span></div></div>
    <div class="tile"><div class="l">{icon("flame")} 活动</div><div class="n" style="color:var(--normal)">{latest.get('active_calories') or '—'}<span style="font-size:11px;color:var(--ink-3)"> kcal</span></div></div>
  </div></div>
</div>"""
write("data.html", "数据", data_inner)

# ── Me ─────────────────────────────────────────────────────────────────────
def setrow(ic, nm, val, on=None):
    right = (f'<span class="chip" style="color:var(--normal);background:var(--normal-bg)">{val}</span>' if on
             else (f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-3)">{esc(val)}</span>' if val else "")
             ) if on is not None else (f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-3)">{esc(val)}</span>' if val else "")
    return (f'<div class="row">{icon(ic, font_size="19px", color="var(--ink-2)")}<span style="flex:1;font-weight:600;font-size:15px;color:var(--ink-1)">{esc(nm)}</span>{right}{icon("chevron-right", font_size="18px", color="var(--ink-4)")}</div>')
me_inner = f"""<div class="topbar"><div><div class="ttl">我的</div></div></div>
<div class="body" style="gap:20px">
  <div class="card p"><div style="display:flex;align-items:center;gap:14px;margin-bottom:16px"><div class="avatar" style="width:54px;height:54px;font-size:22px">{esc(name[:1])}</div><div style="flex:1"><div style="font-weight:800;font-size:19px;color:var(--ink-1)">{esc(name)}</div><div style="font-size:13px;color:var(--ink-3)">{esc(meta)}</div></div></div>
    <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:7px"><span style="font-size:13px;font-weight:600;color:var(--ink-2)">90 天主动管理</span><span style="font-family:var(--font-mono);font-size:13px;color:var(--ink-1)">第 {day or '—'} / 90 天</span></div><div class="prog"><div style="width:{round((day or 0)/90*100)}%"></div></div></div>
  <div><div class="ov">已连接</div><div class="card">
    <div class="row">{icon("watch", font_size="19px", color="var(--ink-2)")}<div style="flex:1"><div style="font-weight:600;font-size:15px;color:var(--ink-1)">Garmin 手环</div><div style="font-size:12.5px;color:var(--normal)">已同步 · {len(garmin)} 天数据</div></div>{icon("check-circle-2", font_size="20px", color="var(--green-500)")}</div>
    <div class="row">{icon("file-text", font_size="19px", color="var(--ink-2)")}<div style="flex:1"><div style="font-weight:600;font-size:15px;color:var(--ink-1)">体检报告</div><div style="font-size:12.5px;color:var(--normal)">{exam.get('exam_date','')} · {esc(exam.get('hospital_name',''))}</div></div>{icon("check-circle-2", font_size="20px", color="var(--green-500)")}</div>
  </div></div>
  <div><div class="ov">设置</div><div class="card">{setrow("bell","每日提醒","")}{setrow("calendar-check","复查提醒","")}{setrow("shield","隐私与数据","")}{setrow("circle-help","帮助与反馈","")}</div></div>
</div>"""
write("me.html", "我的", me_inner)

# ── Index ──────────────────────────────────────────────────────────────────
cards = "".join(f'<a href="{fn}" style="display:block;text-decoration:none"><div class="card p" style="margin-bottom:14px"><div style="font-weight:700;font-size:16px;color:var(--ink-1)">{t}</div><div style="font-size:13px;color:var(--ink-3);margin-top:3px">{fn}</div></div></a>'
                 for fn, t in [("today.html", "今天 Today"), ("data.html", "数据 Data"), ("me.html", "我的 Me")])
idx = HEAD.format(title="索引", date=TODAY.isoformat()) + f'<div class="body"><div class="ov">真实数据设计稿 · user_id=3</div>{cards}</div>' + FOOT
open(os.path.join(HERE, "index.html"), "w", encoding="utf-8").write(idx)
print("wrote index.html")
