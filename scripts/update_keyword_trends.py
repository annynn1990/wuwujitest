#!/usr/bin/env python3
from __future__ import annotations
import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"seo-dashboard"/"trend-data.json"

TERMS={
"核心":["中天法門","中天禪修","中天總壇","一世成就"],
"禪修":["禪修","禪修課程","禪修班","高級禪修班","禪修方式","靜心","冥想","打坐","吉祥坐"],
"修行":["修行","修道","修練","修煉","開悟","心性","內修","外德","生命課題","靈性"],
"宗教":["宗教","佛教","道教","心靈","精神","靈性能量"],
"地區":["台南","東山","台南禪修","東山禪修","中天法門台南","中天法門東山","台南市東山區","中天總壇"],
"意圖":["中天法門是什麼","中天法門在哪裡","中天法門課程","中天法門說明會","怎麼禪修","禪修課程推薦","台南禪修課程","東山禪修課程"]}

PUBLIC=["index.html","about.html","course.html","faq.html","meditation.html","seminar.html"]
AI=["ai-knowledge/index.html","ai-knowledge/llms.txt","ai-knowledge/knowledge.json","ai-knowledge/official/index.json","ai-knowledge/forum/index.json"]

def clean(s):
    s=re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>"," ",s,flags=re.I)
    return re.sub(r"<[^>]+>"," ",s).replace("&nbsp;"," ")

def sources():
    out=[]
    for rel in PUBLIC+AI:
        p=ROOT/rel
        if p.exists():
            try: out.append((rel,p.read_text(encoding="utf-8",errors="replace")))
            except Exception: pass
    return out

def calculate():
    src=sources(); rows=[]
    for group,terms in TERMS.items():
        for term in terms:
            occ=src_n=title_n=head_n=0
            for rel,c in src:
                body=clean(c)
                n=body.lower().count(term.lower())
                # 防止 knowledge.json 的大量重複文字單獨灌高分
                n=min(n,20)
                if n:
                    src_n+=1; occ+=n
                title=" ".join(re.findall(r"<title[^>]*>([\s\S]*?)</title>",c,re.I))
                heads=" ".join(re.findall(r"<h[1-3][^>]*>([\s\S]*?)</h[1-3]>",c,re.I))
                title_n+=bool(term.lower() in title.lower())
                head_n+=bool(term.lower() in clean(heads).lower())
            score=min(100,round(occ*1.6+src_n*6+title_n*14+head_n*8))
            rows.append({"group":group,"term":term,"occurrences":occ,"sources":src_n,"title_sources":title_n,"heading_sources":head_n,"score":score})
    return rows,len(src)

def _parse_google_json(text):
    text=text.lstrip()
    if text.startswith(")]}'"):
        text=text.split("\n",1)[1] if "\n" in text else text[4:]
    return json.loads(text)

def _direct_trends(terms, group):
    """Directly use the same two-step Trends endpoints used by the public Trends web UI.
    This is a fallback for pytrends, which is archived and can receive 429 responses.
    """
    import requests
    sess=requests.Session()
    sess.headers.update({
        "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
        "Accept-Language":"zh-TW,zh;q=0.9,en;q=0.8",
        "Referer":"https://trends.google.com/"
    })
    comparison=[{"keyword":t,"geo":{"country":"TW"},"time":"today 12-m"} for t in terms]
    req={"comparisonItem":comparison,"category":0,"property":""}
    r=sess.get("https://trends.google.com/trends/api/explore",
               params={"hl":"zh-TW","tz":"480","req":json.dumps(req,separators=(",",":"))},
               timeout=25)
    r.raise_for_status()
    payload=_parse_google_json(r.text)
    widgets=payload.get("widgets",[])
    widget=next((w for w in widgets if w.get("id")=="TIMESERIES" or w.get("type")=="TIMESERIES"),None)
    if not widget:
        widget=next((w for w in widgets if "timeseries" in str(w.get("id","")).lower()),None)
    if not widget:
        raise RuntimeError("Google Trends explore 未返回 TIMESERIES widget")
    wreq=widget.get("request")
    token=widget.get("token")
    if not wreq or not token:
        raise RuntimeError("Google Trends 未返回 widget request/token")
    rr=sess.get("https://trends.google.com/trends/api/widgetdata/multiline",
                params={"hl":"zh-TW","tz":"480","req":json.dumps(wreq,separators=(",",":")),
                        "token":token},
                timeout=25)
    rr.raise_for_status()
    data=_parse_google_json(rr.text)
    timeline=data.get("default",{}).get("timelineData",[])
    series={t:[] for t in terms}
    for point in timeline:
        vals=point.get("value",[])
        for i,t in enumerate(terms):
            if i < len(vals):
                try: series[t].append(float(vals[i]))
                except (TypeError,ValueError): series[t].append(0.0)
    result={}
    for term in terms:
        vals=series[term]
        recent=sum(vals[-4:])/len(vals[-4:]) if vals[-4:] else 0
        previous=sum(vals[-8:-4])/len(vals[-8:-4]) if len(vals)>=8 else 0
        average=sum(vals)/len(vals) if vals else 0
        change=((recent-previous)/previous*100) if previous else 0
        result[term]={"term":term,"group":group,"average":average,"recent":recent,
                      "previous":previous,"change_pct":change,"points":len(vals),
                      "explore_url":"https://trends.google.com/trends/explore?geo=TW&q="+quote(term)}
    return result

def trends():
    # Google Trends 每次最多比較少量詞，因此以固定「禪修」作台灣基準，
    # 分批監測全部 TERMS。這不是絕對搜尋量，而是相對搜尋興趣。
    anchor="禪修"
    all_terms=[]
    term_group={}
    for group,terms in TERMS.items():
        for term in terms:
            if term not in all_terms:
                all_terms.append(term)
                term_group[term]=group
    targets=[t for t in all_terms if t != anchor]
    result={}; batches=[]; errors=[]
    for i in range(0,len(targets),4):
        chunk=targets[i:i+4]
        terms=[anchor]+chunk
        groups=sorted({term_group.get(t,"禪修") for t in chunk})
        group="、".join(groups)
        done=False
        try:
            from pytrends.request import TrendReq
            py=TrendReq(hl="zh-TW",tz=480,retries=1,backoff_factor=0.5)
            py.build_payload(terms,cat=0,timeframe="today 12-m",geo="TW",gprop="")
            interest=py.interest_over_time()
            av=interest.mean(numeric_only=True).to_dict()
            anchor_avg=float(av.get(anchor,0) or 0)
            for term in chunk:
                vals=[float(x) for x in interest[term].tolist()] if term in interest else []
                recent=sum(vals[-4:])/len(vals[-4:]) if vals[-4:] else 0
                previous=sum(vals[-8:-4])/len(vals[-8:-4]) if len(vals)>=8 else 0
                average=float(av.get(term,0) or 0)
                change=((recent-previous)/previous*100) if previous else 0
                relative=(average/anchor_avg*100) if anchor_avg else 0
                result[term]={"term":term,"group":term_group.get(term,""),"average":average,
                              "recent":recent,"previous":previous,"change_pct":change,
                              "relative_to_anchor":relative,"anchor":anchor,
                              "anchor_average":anchor_avg,"points":len(vals),
                              "explore_url":"https://trends.google.com/trends/explore?geo=TW&q="+quote(term)}
            done=True
            batches.append({"group":group,"status":"ok","method":"pytrends","terms":chunk,"anchor":anchor})
        except Exception as e:
            errors.append(group+" pytrends: "+type(e).__name__+": "+str(e))
        if not done:
            try:
                direct=_direct_trends(terms,group)
                anchor_avg=float(direct.get(anchor,{}).get("average",0) or 0)
                for term in chunk:
                    if term in direct:
                        direct[term]["relative_to_anchor"]=(
                            float(direct[term].get("average",0) or 0)/anchor_avg*100
                            if anchor_avg else 0)
                        direct[term]["anchor"]=anchor
                        direct[term]["anchor_average"]=anchor_avg
                result.update({k:v for k,v in direct.items() if k != anchor})
                batches.append({"group":group,"status":"ok","method":"direct-trends","terms":chunk,"anchor":anchor})
                done=True
            except Exception as e:
                errors.append(group+" direct: "+type(e).__name__+": "+str(e))
                batches.append({"group":group,"status":"error","terms":chunk,"anchor":anchor,"error":str(e)})
    return {"available":bool(result),"fetched_at":datetime.now(timezone.utc).isoformat(),
            "keywords":result,"batches":batches,
            "error":"；".join(errors) if errors else None,
            "source_note":"Google Trends 台灣 Web Search；全部監測關鍵字分批以「禪修」作固定基準。relative_to_anchor 為相對搜尋興趣，不是實際搜尋人數或使用率。"}

