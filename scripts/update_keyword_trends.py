#!/usr/bin/env python3
from __future__ import annotations
import json,re
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"seo-dashboard"/"trend-data.json"
TERMS={
 "核心":["中天法門","中天禪修","中天總壇","一世成就"],
 "禪修":["禪修","禪修課程","禪修班","高級禪修班","禪修方式","靜心","冥想","打坐","吉祥坐"],
 "修行":["修行","修道","修練","修煉","開悟","心性","內修","外德","生命課題","靈性"],
 "宗教":["宗教","佛教","道教","心靈","精神","靈性能量"],
 "地區":["台南","東山","台南禪修","東山禪修","中天法門台南","中天法門東山","台南市東山區","中天總壇"],
 "意圖":["中天法門是什麼","中天法門在哪裡","中天法門課程","中天法門說明會","怎麼禪修","禪修課程推薦","台南禪修課程","東山禪修課程"],
}
PAGES=[p for p in ROOT.glob("*.html") if p.name not in {"404.html"}]
def strip_html(s):
    s=re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>"," ",s,flags=re.I)
    return re.sub(r"<[^>]+>"," ",s).replace("&nbsp;"," ")
def count(s,t): return s.count(t)
def calculate():
    rows=[]
    for group,words in TERMS.items():
        for term in words:
            occ=pages_n=title_n=head_n=0
            for p in PAGES:
                c=p.read_text(encoding="utf-8",errors="replace")
                body=strip_html(c)
                title=" ".join(re.findall(r"<title>([\s\S]*?)</title>",c,re.I))
                heads=" ".join(strip_html(x) for x in re.findall(r"<h[1-3][^>]*>[\s\S]*?</h[1-3]>",c,re.I))
                n=count(body,term); occ+=n
                pages_n += bool(n)
                title_n += bool(count(title,term))
                head_n += bool(count(heads,term))
            score=min(100,occ*2+pages_n*8+title_n*15+head_n*8)
            rows.append({"group":group,"term":term,"occurrences":occ,"pages":pages_n,"title_pages":title_n,"heading_pages":head_n,"score":score})
    return rows
def load_old():
    try:return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:return {}
def main():
    OUT.parent.mkdir(exist_ok=True)
    rows=calculate(); old=load_old()
    week=datetime.now(timezone.utc).date().isoformat()
    hist=old.get("history",[])
    snap={"week":week,"keywords":[{"term":r["term"],"score":r["score"]} for r in rows]}
    hist=(hist+[snap])[-12:]
    rec=[]
    for r in sorted(rows,key=lambda x:x["score"]):
        if r["score"]<35:
            rec.append({"term":r["term"],"action":"補充可直接回答使用者問題的正文／FAQ／H2，並增加相關頁面的內部連結。"})
        if len(rec)>=12: break
    data={"schema_version":"1.0","type":"site_keyword_trend","generated_at":datetime.now(timezone.utc).isoformat(),"note":"本資料是網站自身 SEO/GEO 語意訊號趨勢，不是 Google Search Console 搜尋量或排名資料。","corpus":{"pages":len(PAGES),"excluded":["ai-knowledge/"]},"groups":TERMS,"keywords":rows,"history":hist,"recommendations":rec}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"generated_at":data["generated_at"],"pages":len(PAGES),"keywords":len(rows),"recommendations":len(rec)},ensure_ascii=False))
if __name__=="__main__":main()
