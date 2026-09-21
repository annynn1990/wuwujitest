import json
import re
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://web.wuwuji.tw/seminar"
OUTPUT_FILE = Path("seminar-data.json")


def fetch_html():

    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


def clean_html(html):

    # 移除 script
    html = re.sub(
        r"<script.*?</script>",
        " ",
        html,
        flags=re.I | re.S
    )

    # 移除 style
    html = re.sub(
        r"<style.*?</style>",
        " ",
        html,
        flags=re.I | re.S
    )

    # 移除 HTML 標籤
    html = re.sub(
        r"<[^>]+>",
        " ",
        html
    )

    # HTML 實體轉換
    html = unescape(html)

    # 空白統一
    html = re.sub(
        r"\s+",
        " ",
        html
    )

    return html.strip()


def parse_events(text):

    # 直接抓：
    #
    # 2026年10月04日(日) 中午 台北大同區長安西路場
    # 13:30開始報到
    # 14:00開始說明會
    # 16:30結束時間
    # 台北市大同區...
    #
    # 完全不依賴 HTML 標籤。

    pattern = re.compile(
        r"""
        (?P<date>
            \d{4}年\d{1,2}月\d{1,2}日
        )
        (?:\([一二三四五六日]\))?
        \s*
        (?:中午\s*)?

        (?P<name>.*?)

        \s+
        (?P<checkin>\d{1,2}:\d{2})
        開始報到

        \s+
        (?P<start>\d{1,2}:\d{2})
        開始說明會

        \s+
        (?P<end>\d{1,2}:\d{2})
        結束時間

        \s+

        (?P<address>.*?)

        (?=
            \s+\d{4}年\d{1,2}月\d{1,2}日
            |
            \s+說明會報名
            |
            $
        )
        """,
        re.VERBOSE
    )

    events = []

    for match in pattern.finditer(text):

        date_text = match.group("date").strip()

        name = match.group("name").strip()

        checkin = match.group("checkin")

        start_time = match.group("start")

        end_time = match.group("end")

        address = match.group("address").strip()


        # 名稱清理
        name = re.sub(
            r"\s+",
            " ",
            name
        )


        # 地址清理
        address = re.sub(
            r"\s+",
            " ",
            address
        )


        # 日期
        date_match = re.match(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            date_text
        )

        if not date_match:
            continue


        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))


        # 開始時間
        start_h, start_m = map(
            int,
            start_time.split(":")
        )


        # 結束時間
        end_h, end_m = map(
            int,
            end_time.split(":")
        )


        start_datetime = (
            f"{year:04d}-{month:02d}-{day:02d}"
            f"T{start_h:02d}:{start_m:02d}:00+08:00"
        )


        end_datetime = (
            f"{year:04d}-{month:02d}-{day:02d}"
            f"T{end_h:02d}:{end_m:02d}:00+08:00"
        )


        events.append({

            "name": name,

            "date_display": date_text,

            "date":
                f"{year:04d}-{month:02d}-{day:02d}",

            "checkin": checkin,

            "start_time": start_time,

            "end_time": end_time,

            "start_datetime":
                start_datetime,

            "end_datetime":
                end_datetime,

            "address": address,

            "source": SOURCE_URL
        })


    # 去除重複
    unique = {}

    for event in events:

        key = (
            event["date"],
            event["name"],
            event["address"]
        )

        unique[key] = event


    events = list(unique.values())


    # 日期排序
    events.sort(
        key=lambda x: (
            x["date"],
            x["start_time"]
        )
    )


    return events


def main():

    print("================================")
    print("中天法門說明會自動同步")
    print("================================")

    print(
        "來源：",
        SOURCE_URL
    )


    # 抓取
    html = fetch_html()

    print(
        "HTML 長度：",
        len(html)
    )


    # 轉成文字
    text = clean_html(html)

    print(
        "文字長度：",
        len(text)
    )


    # 找場次
    events = parse_events(text)

    print(
        "解析到場次：",
        len(events)
    )


    # 顯示結果
    for event in events:

        print(
            event["date_display"],
            "|",
            event["name"],
            "|",
            event["address"]
        )


    # 安全機制
    #
    # 如果抓不到，
    # 就直接 FAILED。
    #
    # 不允許把既有資料清空。

    if len(events) == 0:

        print("")
        print("沒有抓到任何場次。")
        print("停止更新，避免清空舊資料。")
        print("")

        raise RuntimeError(
            "官方頁面有內容，但解析器沒有找到場次。"
        )


    # 台灣時間
    taiwan = timezone(
        timedelta(hours=8)
    )

    updated_at = datetime.now(
        taiwan
    ).isoformat()


    data = {

        "source":
            SOURCE_URL,

        "updated_at":
            updated_at,

        "events":
            events
    }


    # 寫入 JSON
    OUTPUT_FILE.write_text(

        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),

        encoding="utf-8"
    )


    print("")
    print(
        "完成！已更新",
        len(events),
        "個場次。"
    )
    print("")


if __name__ == "__main__":
    main()
