import json
import re
import sys
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://web.wuwuji.tw/seminar"

DATA_FILE = Path("seminar-data.json")
DEBUG_FILE = Path("seminar-debug.json")


def now():
    return datetime.now(
        timezone(timedelta(hours=8))
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


def fetch():

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

        html = response.read().decode(
            "utf-8",
            errors="ignore"
        )

        return response.status, html


def clean(html):

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


def main():

    debug = {
        "ok": False,
        "source": SOURCE_URL,
        "updated_at": now(),
        "http_status": None,
        "html_length": 0,
        "text_length": 0,
        "date_count": 0,
        "checkin_count": 0,
        "start_count": 0,
        "end_count": 0,
        "events_count": 0,
        "error": None
    }

    try:

        print("開始抓取官方頁面")

        status, html = fetch()

        debug["http_status"] = status
        debug["html_length"] = len(html)

        print("HTTP =", status)
        print("HTML =", len(html))

        text = clean(html)

        debug["text_length"] = len(text)

        debug["date_count"] = len(
            re.findall(
                r"\d{4}年\d{1,2}月\d{1,2}日",
                text
            )
        )

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
            "日期 =",
            debug["date_count"]
        )

        print(
            "報到 =",
            debug["checkin_count"]
        )

        print(
            "開始 =",
            debug["start_count"]
        )

        print(
            "結束 =",
            debug["end_count"]
        )


        # 直接抓五個場次區塊
        pattern = re.compile(
            r"""
            (?P<date>
                \d{4}年\d{1,2}月\d{1,2}日
            )

            .*?

            (?P<checkin>
                \d{1,2}:\d{2}
            )
            開始報到

            .*?

            (?P<start>
                \d{1,2}:\d{2}
            )
            開始說明會

            .*?

            (?P<end>
                \d{1,2}:\d{2}
            )
            結束時間

            .*?

            (?P<address>
                (?:台北市|新北市|桃園市|新竹市|新竹縣|
                苗栗縣|台中市|彰化縣|南投縣|雲林縣|
                嘉義市|嘉義縣|台南市|高雄市|屏東縣|
                宜蘭縣|花蓮縣|台東縣|澎湖縣)
                .*?
            )

            (?=
                \d{4}年\d{1,2}月\d{1,2}日
                |說明會報名
                |$
            )
            """,
            re.X
        )

        events = []

        for m in pattern.finditer(text):

            date_text = m.group("date")

            checkin = m.group("checkin")
            start = m.group("start")
            end = m.group("end")

            address = re.sub(
                r"\s+",
                " ",
                m.group("address")
            ).strip()

            events.append({
                "name": "中天法門說明會",
                "date_display": date_text,
                "date": date_text,
                "checkin": checkin,
                "start_time": start,
                "end_time": end,
                "address": address,
                "source": SOURCE_URL
            })

        debug["events_count"] = len(events)

        print(
            "解析場次 =",
            len(events)
        )


        # 成功
        if events:

            data = {
                "source": SOURCE_URL,
                "updated_at": now(),
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
            debug["error"] = None

            save_debug(debug)

            print(
                "成功更新",
                len(events),
                "場"
            )

            return


        # 失敗
        debug["error"] = (
            "成功取得官方頁面，但解析到 0 場"
        )

        save_debug(debug)

        raise RuntimeError(
            "解析到 0 場"
        )


    except Exception as e:

        debug["ok"] = False

        debug["error"] = str(e)

        save_debug(debug)

        print(
            "ERROR:",
            e
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
