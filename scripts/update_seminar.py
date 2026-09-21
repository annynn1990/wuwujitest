import json
import re
import traceback

from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen


SOURCE_URL = "https://web.wuwuji.tw/seminar"

DATA_FILE = Path("seminar-data.json")

DEBUG_FILE = Path("seminar-debug.json")


def taiwan_time():

    return datetime.now(
        timezone(
            timedelta(hours=8)
        )
    ).isoformat()


def save_debug(data):

    DEBUG_FILE.write_text(

        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),

        encoding="utf-8"
    )


def fetch_page():

    request = Request(

        SOURCE_URL,

        headers={
            "User-Agent":
                "Mozilla/5.0"
        }

    )

    with urlopen(
        request,
        timeout=30
    ) as response:

        return (
            response.status,
            response.read().decode(
                "utf-8",
                errors="ignore"
            )
        )


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


def extract_events(text):

    pattern = re.compile(

        r"""
        (?P<date>
            \d{4}年\d{1,2}月\d{1,2}日
        )
        (?:\([一二三四五六日]\))?

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

        re.X
    )


    events = []


    for match in pattern.finditer(text):

        date_text = match.group(
            "date"
        )

        body = match.group(
            "body"
        ).strip()


        checkin_match = re.search(
            r"(\d{1,2}:\d{2})\s*開始報到",
            body
        )


        start_match = re.search(
            r"(\d{1,2}:\d{2})\s*開始說明會",
            body
        )


        end_match = re.search(
            r"(\d{1,2}:\d{2})\s*結束時間",
            body
        )


        if not (
            checkin_match
            and start_match
            and end_match
        ):

            continue


        checkin = checkin_match.group(1)

        start = start_match.group(1)

        end = end_match.group(1)


        # 去掉開頭的「中午」
        body = re.sub(
            r"^中午\s*",
            "",
            body
        )


        # 找時間以前的名稱
        name_match = re.search(

            r"^(.*?)"
            r"\s+"
            r"\d{1,2}:\d{2}"
            r"\s*開始報到",

            body

        )


        name = (

            name_match.group(1).strip()

            if name_match

            else "中天法門說明會"

        )


        # 地址通常從縣市開始
        address_match = re.search(

            r"((?:台北市|新北市|桃園市|"
            r"新竹市|新竹縣|苗栗縣|"
            r"台中市|彰化縣|南投縣|"
            r"雲林縣|嘉義市|嘉義縣|"
            r"台南市|高雄市|屏東縣|"
            r"宜蘭縣|花蓮縣|台東縣|澎湖縣).*)",

            body

        )


        address = (

            address_match.group(1).strip()

            if address_match

            else ""

        )


        date_match = re.match(

            r"(\d{4})年(\d{1,2})月(\d{1,2})日",

            date_text

        )


        if not date_match:

            continue


        year = int(
            date_match.group(1)
        )

        month = int(
            date_match.group(2)
        )

        day = int(
            date_match.group(3)
        )


        start_h, start_m = map(
            int,
            start.split(":")
        )


        end_h, end_m = map(
            int,
            end.split(":")
        )


        events.append({

            "name":
                name,

            "date_display":
                date_text,

            "date":
                f"{year:04d}-{month:02d}-{day:02d}",

            "checkin":
                checkin,

            "start_time":
                start,

            "end_time":
                end,

            "start_datetime":
                (
                    f"{year:04d}-{month:02d}-{day:02d}"
                    f"T{start_h:02d}:{start_m:02d}:00+08:00"
                ),

            "end_datetime":
                (
                    f"{year:04d}-{month:02d}-{day:02d}"
                    f"T{end_h:02d}:{end_m:02d}:00+08:00"
                ),

            "address":
                address,

            "source":
                SOURCE_URL

        })


    return events


def main():

    debug = {

        "ok": False,

        "source": SOURCE_URL,

        "time": taiwan_time(),

        "http_status": None,

        "html_length": 0,

        "text_length": 0,

        "dates_found": [],

        "date_count": 0,

        "checkin_count": 0,

        "start_count": 0,

        "end_count": 0,

        "events_count": 0,

        "events": [],

        "error": None,

        "traceback": None

    }


    try:

        print("開始抓取官方頁面")

        print(SOURCE_URL)


        status, html = fetch_page()


        debug["http_status"] = status

        debug["html_length"] = len(html)


        print(
            "HTTP:",
            status
        )


        print(
            "HTML:",
            len(html),
            "bytes"
        )


        text = clean_html(html)


        debug["text_length"] = len(text)


        print(
            "TEXT:",
            len(text),
            "bytes"
        )


        # 找日期
        dates = re.findall(

            r"\d{4}年\d{1,2}月\d{1,2}日",

            text

        )


        debug["dates_found"] = dates[:50]

        debug["date_count"] = len(dates)


        # 找時間文字

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


        print(
            "日期數量：",
            debug["date_count"]
        )


        print(
            "報到數量：",
            debug["checkin_count"]
        )


        print(
            "開始數量：",
            debug["start_count"]
        )


        print(
            "結束數量：",
            debug["end_count"]
        )


        events = extract_events(text)


        debug["events_count"] = len(events)

        debug["events"] = events


        print(
            "解析場次：",
            len(events)
        )


        if not events:

            debug["error"] = (
                "解析到 0 場"
            )

            save_debug(debug)

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

            "source":
                SOURCE_URL,

            "updated_at":
                taiwan_time(),

            "events":
                events

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

        debug["error"] = None

        save_debug(debug)


        print(
            "✅ 完成"
        )


    except Exception as error:

        debug["error"] = str(error)

        debug["traceback"] = (
            traceback.format_exc()
        )


        save_debug(debug)


        print(
            "❌ 錯誤：",
            error
        )


        raise


if __name__ == "__main__":
    main()
