import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://web.wuwuji.tw/seminar"
OUTPUT = Path("seminar-data.json")


def fetch_page():
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent":
                "Mozilla/5.0 (compatible; ZhongtianInfoBot/1.0)"
        }
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


def html_to_text(html):

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

    html = html.replace("&nbsp;", " ")

    html = re.sub(r"\s+", " ", html)

    return html.strip()


def extract_events(text):

    pattern = re.compile(
        r"""
        (?P<date>
            \d{4}年\d{1,2}月\d{1,2}日
            (?:\([一二三四五六日]\))?
        )
        (?P<body>.*?)
        (?=
            \d{4}年\d{1,2}月\d{1,2}日
            |說明會報名
            |$)
        """,
        re.X
    )

    results = []

    for match in pattern.finditer(text):

        date_display = match.group("date").strip()
        body = match.group("body").strip()

        if (
            "報到" not in body
            and "說明會" not in body
            and "場" not in body
        ):
            continue

        name_match = re.search(
            r"(?:中午\s*)?(.{2,80}?)(?=\s*\d{1,2}:\d{2}\s*開始報到)",
            body
        )

        name = (
            name_match.group(1).strip()
            if name_match
            else "中天法門說明會"
        )

        checkin_match = re.search(
            r"(\d{1,2}:\d{2})\s*開始報到",
            body
        )

        checkin = (
            checkin_match.group(1)
            if checkin_match
            else ""
        )

        start_match = re.search(
            r"(\d{1,2}:\d{2})\s*開始說明會",
            body
        )

        start_time = (
            start_match.group(1)
            if start_match
            else ""
        )

        end_match = re.search(
            r"(\d{1,2}:\d{2})\s*結束時間",
            body
        )

        end_time = (
            end_match.group(1)
            if end_match
            else ""
        )

        address_match = re.search(
            r"((?:台北市|新北市|桃園市|新竹市|新竹縣|苗栗縣|"
            r"台中市|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|"
            r"台南市|高雄市|屏東縣|宜蘭縣|花蓮縣|台東縣|澎湖縣).*)",
            body
        )

        address = (
            address_match.group(1).strip()
            if address_match
            else ""
        )

        date_match = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            date_display
        )

        if not date_match:
            continue

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        start_datetime = ""
        end_datetime = ""

        if start_time:

            h, m = map(
                int,
                start_time.split(":")
            )

            start_datetime = (
                f"{year:04d}-{month:02d}-{day:02d}"
                f"T{h:02d}:{m:02d}:00+08:00"
            )

        if end_time:

            h, m = map(
                int,
                end_time.split(":")
            )

            end_datetime = (
                f"{year:04d}-{month:02d}-{day:02d}"
                f"T{h:02d}:{m:02d}:00+08:00"
            )

        results.append({

            "name": name,

            "date_display": date_display,

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

    unique = {}

    for event in results:

        key = (
            event["date"],
            event["name"],
            event["address"]
        )

        unique[key] = event

    return list(unique.values())


def main():

    html = fetch_page()

    text = html_to_text(html)

    events = extract_events(text)

    taiwan = timezone(
        timedelta(hours=8)
    )

    now = datetime.now(
        taiwan
    ).isoformat()

    data = {

        "source": SOURCE_URL,

        "updated_at": now,

        "events": events

    }

    OUTPUT.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"同步完成，共抓到 {len(events)} 個場次。"
    )


if __name__ == "__main__":
    main()