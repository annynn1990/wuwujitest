import json
import re
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = "https://web.wuwuji.tw/seminar"
OUTPUT_FILE = Path("seminar-data.json")


class ListParser(HTMLParser):
    """只抓網頁中的 <li> 文字"""

    def __init__(self):
        super().__init__()
        self.in_li = False
        self.current = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "li":
            self.in_li = True
            self.current = []

    def handle_endtag(self, tag):
        if tag.lower() == "li" and self.in_li:
            text = " ".join(self.current)
            text = re.sub(r"\s+", " ", text).strip()

            if text:
                self.items.append(text)

            self.in_li = False
            self.current = []

    def handle_data(self, data):
        if self.in_li:
            text = data.strip()

            if text:
                self.current.append(text)


def fetch_html():
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/140 Safari/537.36"
            )
        }
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def parse_events(html):
    parser = ListParser()
    parser.feed(html)

    events = []

    pattern = re.compile(
        r"(?P<date>\d{4}年\d{1,2}月\d{1,2}日)"
        r"(?:\([一二三四五六日]\))?"
        r"\s*"
        r"(?P<name>.*?)"
        r"\s+(?P<checkin>\d{1,2}:\d{2})開始報到"
        r"\s+(?P<start>\d{1,2}:\d{2})開始說明會"
        r"\s+(?P<end>\d{1,2}:\d{2})結束時間"
        r"\s+(?P<address>.+)$"
    )

    for item in parser.items:

        match = pattern.search(item)

        if not match:
            continue

        date_text = match.group("date")
        name = match.group("name").strip()
        checkin = match.group("checkin")
        start = match.group("start")
        end = match.group("end")
        address = match.group("address").strip()

        # 清理名稱
        name = re.sub(r"^中午\s*", "", name)
        name = re.sub(r"\s+", " ", name)

        # 清理地址
        address = re.sub(r"\s+", " ", address)

        # 解析日期
        date_match = re.match(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            date_text
        )

        if not date_match:
            continue

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        start_h, start_m = map(int, start.split(":"))
        end_h, end_m = map(int, end.split(":"))

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
            "date": (
                f"{year:04d}-{month:02d}-{day:02d}"
            ),
            "checkin": checkin,
            "start_time": start,
            "end_time": end,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "address": address,
            "source": SOURCE_URL
        })

    return events


def main():

    print("開始抓取：")
    print(SOURCE_URL)

    html = fetch_html()

    print(
        f"成功取得網頁，HTML 長度：{len(html)}"
    )

    events = parse_events(html)

    print(
        f"成功解析場次：{len(events)}"
    )

    # 非常重要：
    # 抓不到場次時直接失敗，
    # 不更新 seminar-data.json。
    if not events:
        raise RuntimeError(
            "沒有抓到任何說明會場次，"
            "因此停止更新，避免把舊資料清空。"
        )

    # 排序
    events.sort(
        key=lambda x: (
            x["date"],
            x["start_time"],
            x["name"]
        )
    )

    # 台灣時間
    taiwan = timezone(
        timedelta(hours=8)
    )

    updated_at = datetime.now(
        taiwan
    ).isoformat()

    data = {
        "source": SOURCE_URL,
        "updated_at": updated_at,
        "events": events
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"完成！已寫入 {len(events)} 個場次。"
    )


if __name__ == "__main__":
    main()
