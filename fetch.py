# -*- coding: utf-8 -*-
"""
每日简报自动抓取脚本（澎湃新闻 + 天气）
运行环境：GitHub Actions（也可以本地 python3 fetch.py 手动跑）
产物：
  1. jianbao-YYYY-MM-DD.html —— 当天简报页（按北京时间日期）
  2. index.html —— 目录页（自动重建，最新一期在最上面）
依赖：仅 Python 标准库，不需要 pip 安装任何东西
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

# ================= 配置区（按需修改） =================
# 天气城市：改成你自己城市的名称和经纬度（经纬度可搜“城市名 经纬度”）
CITY_NAME = "武汉"
LAT, LON = 30.5928, 114.3055

# 澎湃频道：(频道ID, 频道名)，常用：
#   25950 时事 | 25951 财经 | 119908 科技 | 122908 国际 | -21 体育 | 25953 生活 | 25952 思想
CHANNELS = [
    (25950, "时事"),
    (119908, "科技"),
]
PER_CHANNEL = 10      # 每个频道最多取几条
MAX_ITEMS = 20        # 简报页总条数上限
# =====================================================

TZ = ZoneInfo("Asia/Shanghai")
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")
OUT_PAGE = f"jianbao-{TODAY}.html"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def http_post_json(url, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------- 澎湃新闻 ----------------
def fetch_thepaper(channel_id, channel_name):
    """澎湃官方接口（RSSHub 开源代码同款）：按频道返回最新文章列表。"""
    url = "https://api.thepaper.cn/contentapi/nodeCont/getByChannelId"
    resp = http_post_json(url, {"channelId": channel_id})
    items = ((resp.get("data") or {}).get("list")) or []
    if items:
        # 方便第一次运行时在 Actions 日志里核对字段名
        print(f"[澎湃/{channel_name}] 返回 {len(items)} 条，首条字段：{list(items[0].keys())}",
              file=sys.stderr)
    out = []
    for it in items[:PER_CHANNEL]:
        title = it.get("name") or it.get("title") or ""
        cont_id = it.get("contId") or it.get("contentId") or it.get("id") or ""
        link = it.get("link") or (f"https://www.thepaper.cn/newsDetail_forward_{cont_id}"
                                   if cont_id else "https://www.thepaper.cn")
        ts = it.get("pubTimeLong") or it.get("publishTimeLong") or 0
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            ts = 0
        summary = it.get("summary") or it.get("description") or ""
        if title:
            out.append({"title": title, "link": link, "ts": ts,
                        "summary": summary, "source": f"澎湃·{channel_name}"})
    return out


# ---------------- 天气（Open-Meteo，免费无 key） ----------------
WMO = {0: "晴", 1: "多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾",
       51: "小雨", 53: "小雨", 55: "中雨", 61: "小雨", 63: "中雨", 65: "大雨",
       66: "雨", 67: "雨", 71: "小雪", 73: "中雪", 75: "大雪", 77: "雪",
       80: "阵雨", 81: "阵雨", 82: "暴雨", 85: "阵雪", 86: "阵雪",
       95: "雷阵雨", 96: "雷阵雨", 99: "雷阵雨"}


def fetch_weather():
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={LAT}&longitude={LON}"
           "&current=temperature_2m,weather_code"
           "&daily=temperature_2m_max,temperature_2m_min,weather_code"
           "&timezone=Asia%2FShanghai&forecast_days=3")
    d = http_get_json(url)
    cur = d.get("current") or {}
    daily = d.get("daily") or {}
    days = []
    for i, date in enumerate((daily.get("time") or [])[:3]):
        days.append({
            "date": date,
            "text": WMO.get((daily.get("weather_code") or [0])[i], ""),
            "hi": round((daily.get("temperature_2m_max") or [0])[i]),
            "lo": round((daily.get("temperature_2m_min") or [0])[i]),
        })
    return {"now": round(cur.get("temperature_2m", 0)),
            "text": WMO.get(cur.get("weather_code", 0), ""), "days": days}


# ---------------- 页面生成 ----------------
PAGE_CSS = """
  body { margin:0; background:#f6f4ef; color:#26241f; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:32px 20px 48px; }
  h1 { font-size:27px; margin:0 0 6px; }
  .sub { color:#8a8474; font-size:14px; margin-bottom:22px; }
  .wx { background:#fff; border:1px solid #e7e2d6; border-radius:12px; padding:16px 18px; margin-bottom:22px; font-size:16px; line-height:1.9; }
  .item { background:#fff; border:1px solid #e7e2d6; border-radius:12px; padding:16px 18px; margin-bottom:12px; }
  .item a { color:#26241f; text-decoration:none; font-size:18px; font-weight:600; line-height:1.6; }
  .meta { color:#8a8474; font-size:13.5px; margin-top:4px; }
  .sum { font-size:15.5px; line-height:1.85; color:#4d4636; margin-top:8px; }
  ul.idx { list-style:none; margin:0; padding:0; }
  ul.idx li { background:#fff; border:1px solid #e7e2d6; border-radius:12px; margin-bottom:12px; }
  ul.idx li a { display:block; padding:16px 18px; color:#26241f; text-decoration:none; font-size:17px; }
"""


def fmt_time(ts_ms):
    if not ts_ms:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000, TZ).strftime("%m-%d %H:%M")


def render_daily(news, weather):
    wx_html = ""
    if weather:
        rows = " · ".join(
            f"{d['date'][5:]} {d['text']} {d['lo']}~{d['hi']}℃" for d in weather["days"])
        wx_html = (f'<div class="wx">📍 {esc(CITY_NAME)} · 现在 {esc(weather["text"])} '
                   f'{weather["now"]}℃<br>{esc(rows)}</div>')
    items_html = ""
    for n in news:
        sum_html = f'<div class="sum">{esc(n["summary"])}</div>' if n["summary"] else ""
        items_html += (f'<div class="item"><a href="{esc(n["link"])}" target="_blank" '
                       f'rel="noopener">{esc(n["title"])}</a>'
                       f'<div class="meta">{esc(n["source"])} · {fmt_time(n["ts"])}</div>'
                       f'{sum_html}</div>\n')
    if not items_html:
        items_html = '<div class="item">今天没有抓到条目，可能是接口临时异常，看 Actions 日志排查。</div>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>今日简报 · {TODAY}</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>今日简报 · {TODAY}</h1>
  <div class="sub">澎湃新闻自动抓取 · 点标题看原文</div>
  {wx_html}
  {items_html}
</div>
</body>
</html>
"""


def render_index():
    files = sorted((f for f in os.listdir(".")
                    if re.fullmatch(r"jianbao-\d{4}-\d{2}-\d{2}\.html", f)),
                   reverse=True)
    lis = "\n".join(
        f'    <li><a href="{f}">今日简报 · {f[8:18]}</a></li>' for f in files)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日简报</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>每日简报</h1>
  <div class="sub">澎湃新闻 · 天气 · 自动更新</div>
  <ul class="idx">
{lis}
  </ul>
</div>
</body>
</html>
"""


def main():
    news, seen = [], set()
    for cid, cname in CHANNELS:
        try:
            for n in fetch_thepaper(cid, cname):
                if n["link"] not in seen:
                    seen.add(n["link"])
                    news.append(n)
        except Exception as e:  # 单个频道失败不影响整期
            print(f"[澎湃/{cname}] 抓取失败：{e}", file=sys.stderr)
    news.sort(key=lambda x: x["ts"], reverse=True)
    news = news[:MAX_ITEMS]

    weather = None
    try:
        weather = fetch_weather()
    except Exception as e:
        print(f"[天气] 抓取失败：{e}", file=sys.stderr)

    with open(OUT_PAGE, "w", encoding="utf-8") as f:
        f.write(render_daily(news, weather))
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_index())
    print(f"完成：{OUT_PAGE}（{len(news)} 条）")


if __name__ == "__main__":
    main()
