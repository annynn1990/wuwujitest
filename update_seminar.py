import json
import re
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://web.wuwuji.tw/seminar"

DATA_FILE = Path("seminar-data.json")
DEBUG_FILE = Path("seminar-debug.json")


def get_taiwan_time():
    return datetime.now(
        timezone(timedelta(hours=8))
    ).isoformat()


def fetch_page():

    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(request, timeout=30) as response:

        html = response.read().decode(
            "utf-8",
            errors="ignore"
        )

        return response.status, html


def clean_html(html):

    html = re.sub(
        r"<script.*?</script>",
        " ",
        html,
        flags=re.I | re.S
    )

    html = re.sub(
        r"<style.*?</style>",
        " ",
        html,
        flags=re.I | re.S
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html
    )

    html = unescape(html)

    html = re.sub(
        r"\s+",
        " ",
        html
    )

    return html.strip()


def find_events(text):

    pattern = re.compile(
        r"""
        (?P<date>
            \d{4}年\d{1,2}月\d{1,2}日
        )

        (?:\([一二三四五六日]\))?

        \s*

        (?P<body>
            .*?
        )

        (?=
            \d{4}年\d{1,2}月\d{1,2}日
            |
            說明會報名
            |
            $
        )
        """,
        re.VERBOSE
    )

    events = []

    for match in pattern.finditer(text):

        date_text = match.group("date")

        body = match.group("body").strip()

        checkin = re.search(
            r"(\d{1,2}:\d{2})\s*開始報到",
            body
        )

        start = re.search(
            r"(\d{1,2}:\d{2})\s*開始說明會",
            body
        )

        end = re.search(
            r"(\d{1,2}:\d{2})\s*結束時間",
            body
        )

        if not checkin:
            continue

        if not start:
            continue

        if not end:
            continue

        date_match = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            date_text
        )

        if not date_match:
            continue

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        start_time = start.group(1)
        end_time = end.group(1)
        checkin_time = checkin.group(1)

        # 活動名稱
        name_match = re.search(
            r"^(.*?)\s+\d{1,2}:\d{2}\s*開始報到",
            body
        )

        if name_match:
            name = name_match.group(1).strip()
        else:
            name = "中天法門說明會"

        # 地址
        address_match = re.search(
            r"((?:台北市|新北市|桃園市|新竹市|"
            r"新竹縣|苗栗縣|台中市|彰化縣|"
            r"南投縣|雲林縣|嘉義市|嘉義縣|"
            r"台南市|高雄市|屏東縣|宜蘭縣|"
            r"花蓮縣|台東縣|澎湖縣).*)",
            body
        )

        if address_match:
            address = address_match.group(1).strip()
        else:
            address = ""

        start_h, start_m = map(
            int,
            start_time.split(":")
        )

        end_h, end_m = map(
            int,
            end_time.split(":")
        )

        events.append({

            "name": name,

            "date_display": date_text,

            "date":
                f"{year:04d}-{month:02d}-{day:02d}",

            "checkin":
                checkin_time,

            "start_time":
                start_time,

            "end_time":
                end_time,

            "start_datetime":
                f"{year:04d}-{month:02d}-{day:02d}"
                f"T{start_h:02d}:{start_m:02d}:00+08:00",

            "end_datetime":
                f"{year:04d}-{month:02d}-{day:02d}"
                f"T{end_h:02d}:{end_m:02d}:00+08:00",

            "address":
                address,

            "source":
                SOURCE_URL
        })

    return events


def main():

    debug = {
        "time": get_taiwan_time(),
        "source": SOURCE_URL,
        "http_status": None,
        "html_length": 0,
        "text_length": 0,
        "date_count": 0,
        "checkin_count": 0,
        "start_count": 0,
        "end_count": 0,
        "events_count": 0,
        "events": [],
        "error": None
    }

    try:

        print("開始抓取官方頁面")

        status, html = fetch_page()

        debug["http_status"] = status
        debug["html_length"] = len(html)

        print(
            "HTTP：",
            status
        )

        print(
            "HTML 長度：",
            len(html)
        )

        text = clean_html(html)

        debug["text_length"] = len(text)

        dates = re.findall(
            r"\d{4}年\d{1,2}月\d{1,2}日",
            text
        )

        debug["date_count"] = len(dates)

        debug["checkin_count"] = len(
            re.findall(
                r"\d{1,2}:\d{2}\s*開始報到",
                text
            )
        )

        debug["start_count"] = len(
            re.findall(
                r"\d{1,2}:\d{2}\s*開始說明會",
                text
            )
        )

        debug["end_count"] = len(
            re.findall(
                r"\d{1,2}:\d{2}\s*結束時間",
                text
            )
        )

        events = find_events(text)

        debug["events_count"] = len(events)
        debug["events"] = events

        print(
            "日期：",
            debug["date_count"]
        )

        print(
            "報到：",
            debug["checkin_count"]
        )

        print(
            "開始：",
            debug["start_count"]
        )

        print(
            "結束：",
            debug["end_count"]
        )

        print(
            "解析場次：",
            len(events)
        )

        if not events:

            debug["error"] = (
                "官方頁面取得成功，但解析到 0 場"
            )

            DEBUG_FILE.write_text(
                json.dumps(
                    debug,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            raise RuntimeError(
                "解析到 0 場"
            )

        events.sort(
            key=lambda x: (
                x["date"],
                x["start_time"]
            )
        )

        data = {
            "source": SOURCE_URL,
            "updated_at": get_taiwan_time(),
            "events": events
        }

        DATA_FILE.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        debug["ok"] = True

        DEBUG_FILE.write_text(
            json.dumps(
                debug,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        print(
            "成功寫入：",
            len(events),
            "場"
        )

    except Exception as error:

        debug["error"] = str(error)

        DEBUG_FILE.write_text(
            json.dumps(
                debug,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        raise


if __name__ == "__main__":
    main()
