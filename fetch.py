# -*- coding: utf-8 -*-
"""
每日简报自动抓取脚本 v2（澎湃首页头条 + 天气）
运行环境：GitHub Actions（也可以本地 python3 fetch.py 手动跑）
产物：
  1. jianbao-YYYY-MM-DD.html —— 当天简报页（按北京时间日期）
  2. index.html —— 目录页（自动重建，最新一期在最上面）
依赖：仅 Python 标准库，不需要 pip 安装任何东西
数据来源：澎湃手机版首页 m.thepaper.cn 内嵌的 __NEXT_DATA__（与 RSSHub 头条路由同源），
         取首页文章列表，保持编辑排好的原始顺序，不按时间重排。
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

MAX_ITEMS = 20        # 头条最多取几条
# =====================================================

TZ = ZoneInfo("Asia/Shanghai")
TODAY = datetime.now(TZ).strftime("%Y-%m-%d")
OUT_PAGE = f"jianbao-{TODAY}.html"
UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"}


def http_get_text(url, timeout=30, extra_headers=None):
    req = urllib.request.Request(url, headers={**UA, **(extra_headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def parse_item(it):
    """容错解析一篇文章条目（字段名以澎湃现行结构为主，取不到就跳过）。"""
    title = it.get("name") or it.get("title") or ""
    if not title:
        return None
    cont_id = it.get("contId") or it.get("contentId") or it.get("id") or ""
    link = it.get("link") or it.get("url") or (
        f"https://www.thepaper.cn/newsDetail_forward_{cont_id}" if cont_id
        else "https://www.thepaper.cn")
    ts = it.get("pubTimeLong") or it.get("publishTimeLong") or 0
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        ts = 0
    summary = it.get("summary") or it.get("description") or ""
    return {"title": title, "link": link, "ts": ts, "summary": summary,
            "source": "澎湃·头条"}


# ---------------- 澎湃首页头条 ----------------
def fetch_featured():
    html = http_get_text("https://m.thepaper.cn",
                         extra_headers={"Cookie": "blackAndWhiteMode=0; redTops=0;"})
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("页面里没找到 __NEXT_DATA__，澎湃可能改版了")
    data = json.loads(m.group(1))
    page_props = ((data.get("props") or {}).get("pageProps") or {})
    main_list = ((page_props.get("data") or {}).get("list")) or []
    top_list = ((page_props.get("topData") or {}).get("recommendImg")) or []
    raw = list(main_list) + list(top_list)
    if raw:
        print(f"[澎湃头条] 原始 {len(raw)} 条，首条字段：{list(raw[0].keys())}",
              file=sys.stderr)
    out, seen = [], set()
    for it in raw:
        n = parse_item(it)
        if n and n["link"] not in seen:
            seen.add(n["link"])
            out.append(n)
        if len(out) >= MAX_ITEMS:
            break
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
        t = fmt_time(n["ts"])
        meta = f'{esc(n["source"])} · {t}' if t else esc(n["source"])
        items_html += (f'<div class="item"><a href="{esc(n["link"])}" target="_blank" '
                       f'rel="noopener">{esc(n["title"])}</a>'
                       f'<div class="meta">{meta}</div>{sum_html}</div>\n')
    if not items_html:
        items_html = '<div class="item">今天没有抓到条目，可能是澎湃改版或临时异常，看 Actions 日志排查。</div>'
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
  <div class="sub">澎湃首页头条自动抓取 · 点标题看原文</div>
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
  <div class="sub">澎湃头条 · 天气 · 自动更新</div>
  <ul class="idx">
{lis}
  </ul>
</div>
</body>
</html>
"""


def main():
    news = []
    try:
        news = fetch_featured()
    except Exception as e:
        print(f"[澎湃头条] 抓取失败：{e}", file=sys.stderr)

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
