import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from html import unescape

SOURCE_URL = "https://web.wuwuji.tw/seminar"
OUTPUT = Path("seminar-data.json")


def fetch_page():
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/140 Safari/537.36"
            )
        },
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def html_to_text(html):
    # 移除 script / style
    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )

    # 保留文字
    html = re.sub(r"<[^>]+>", " ", html)

    html = unescape(html)

    # 統一空白
    html = html.replace("\xa0", " ")
    html = re.sub(r"\s+", " ", html)

    return html.strip()


def extract_events(text):
    """
    不再要求「日期區塊」一定出現特定關鍵字。
    只要找到：
      日期
      報到時間
      開始時間
      結束時間

    就建立一個場次。
    """

    date_pattern = re.compile(
        r"\d{4}年\d{1,2}月\d{1,2}日"
        r"(?:\s*[（(][一二三四五六日天][）)])?"
    )

    time_pattern = re.compile(r"\d{1,2}:\d{2}")

    date_matches = list(date_pattern.finditer(text))

    print(f"找到日期區塊 = {len(date_matches)}")

    results = []

    for index, date_match in enumerate(date_matches):
        date_display = date_match.group(0).strip()

        start_pos = date_match.start()

        if index + 1 < len(date_matches):
            end_pos = date_matches[index + 1].start()
        else:
            end_pos = len(text)

        body = text[start_pos:end_pos].strip()

        # 日期
        parsed_date = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            date_display,
        )

        if not parsed_date:
            continue

        year = int(parsed_date.group(1))
        month = int(parsed_date.group(2))
        day = int(parsed_date.group(3))

        # 報到
        checkin_match = re.search(
            r"(\d{1,2}:\d{2})\s*開始報到",
            body,
        )

        # 開始
        start_match = re.search(
            r"(\d{1,2}:\d{2})\s*開始(?:說明會|講座|活動)?",
            body,
        )

        # 結束
        end_match = re.search(
            r"(\d{1,2}:\d{2})\s*結束(?:時間|說明會|講座|活動)?",
            body,
        )

        checkin = (
            checkin_match.group(1)
            if checkin_match
            else ""
        )

        start_time = (
            start_match.group(1)
            if start_match
            else ""
        )

        end_time = (
            end_match.group(1)
            if end_match
            else ""
        )

        # 如果「開始」沒有抓到，
        # 嘗試直接找這個日期區塊中的時間
        if not start_time:
            times = time_pattern.findall(body)

            if len(times) >= 2:
                start_time = times[1]

        # 如果「結束」沒有抓到，
        # 嘗試直接使用最後一個時間
        if not end_time:
            times = time_pattern.findall(body)

            if len(times) >= 3:
                end_time = times[-1]

        # 報到時間沒有抓到也不要直接丟掉
        if not checkin:
            times = time_pattern.findall(body)

            if len(times) >= 1:
                checkin = times[0]

        # 至少要有開始時間才算一場
        if not start_time:
            print(
                f"跳過：{date_display} "
                f"找不到開始時間"
            )
            continue

        # 名稱
        name = "中天法門說明會"

        name_match = re.search(
            r"(.{2,80}?)\s*"
            r"\d{1,2}:\d{2}\s*開始報到",
            body,
        )

        if name_match:
            candidate = name_match.group(1).strip()

            # 避免把日期一起當名稱
            candidate = re.sub(
                r"^\d{4}年\d{1,2}月\d{1,2}日"
                r"(?:\s*[（(][一二三四五六日天][）)])?",
                "",
                candidate,
            ).strip()

            if candidate:
                name = candidate

        # 地址
        address_match = re.search(
            r"("
            r"台北市|新北市|桃園市|新竹市|新竹縣|苗栗縣|"
            r"台中市|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|"
            r"台南市|高雄市|屏東縣|宜蘭縣|花蓮縣|"
            r"台東縣|澎湖縣"
            r").{0,150}",
            body,
        )

        address = (
            address_match.group(0).strip()
            if address_match
            else ""
        )

        # ISO datetime
        start_datetime = ""
        end_datetime = ""

        if start_time:
            h, m = map(int, start_time.split(":"))

            start_datetime = (
                f"{year:04d}-{month:02d}-{day:02d}"
                f"T{h:02d}:{m:02d}:00+08:00"
            )

        if end_time:
            h, m = map(int, end_time.split(":"))

            end_datetime = (
                f"{year:04d}-{month:02d}-{day:02d}"
                f"T{h:02d}:{m:02d}:00+08:00"
            )

        event = {
            "name": name,
            "date_display": date_display,
            "date": (
                f"{year:04d}-"
                f"{month:02d}-"
                f"{day:02d}"
            ),
            "checkin": checkin,
            "start_time": start_time,
            "end_time": end_time,
            "start_datetime": start_datetime,
            "end_datetime": end_datetime,
            "address": address,
            "source": SOURCE_URL,
        }

        results.append(event)

        print(
            f"解析成功：{date_display} "
            f"報到={checkin} "
            f"開始={start_time} "
            f"結束={end_time}"
        )

    # 去除重複
    unique = {}

    for event in results:
        key = (
            event["date"],
            event["name"],
            event["address"],
        )

        unique[key] = event

    return list(unique.values())


def main():
    print("開始抓取官方頁面")

    html = fetch_page()

    print(f"HTTP = 200")
    print(f"HTML = {len(html)}")

    text = html_to_text(html)

    # 保留原本的診斷資訊
    print(
        f"日期 = "
        f"{len(re.findall(r'\\d{4}年\\d{1,2}月\\d{1,2}日', text))}"
    )

    print(
        f"報到 = "
        f"{len(re.findall(r'\\d{1,2}:\\d{2}\\s*開始報到', text))}"
    )

    print(
        f"開始 = "
        f"{len(re.findall(r'\\d{1,2}:\\d{2}\\s*開始', text))}"
    )

    print(
        f"結束 = "
        f"{len(re.findall(r'\\d{1,2}:\\d{2}\\s*結束', text))}"
    )

    events = extract_events(text)

    print(f"解析場次 = {len(events)}")

    # 寫出 JSON
    taiwan = timezone(timedelta(hours=8))

    now = datetime.now(taiwan).isoformat()

    data = {
        "source": SOURCE_URL,
        "updated_at": now,
        "events": events,
    }

    OUTPUT.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if not events:
        print("ERROR: 解析到 0 場")
        raise SystemExit(1)

    print(
        f"同步完成，共抓到 {len(events)} 個場次。"
    )


if __name__ == "__main__":
    main()
