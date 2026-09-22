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
    groups=[
        ("修行與禪修",["禪修","修行","修道","冥想","靈性"]),
        ("宗教與靜坐",["打坐","靜坐","佛教","道教","宗教"]),
        ("中天與地區",["中天法門","中天法門台南","中天法門東山","台南禪修","東山禪修"])
    ]
    result={}; batches=[]; errors=[]
    for group,terms in groups:
        done=False
        try:
            from pytrends.request import TrendReq
            py=TrendReq(hl="zh-TW",tz=480,retries=1,backoff_factor=0.5)
            py.build_payload(terms,cat=0,timeframe="today 12-m",geo="TW",gprop="")
            interest=py.interest_over_time()
            av=interest.mean(numeric_only=True).to_dict()
            for term in terms:
                vals=[float(x) for x in interest[term].tolist()] if term in interest else []
                recent=sum(vals[-4:])/len(vals[-4:]) if vals[-4:] else 0
                previous=sum(vals[-8:-4])/len(vals[-8:-4]) if len(vals)>=8 else 0
                average=float(av.get(term,0) or 0)
                change=((recent-previous)/previous*100) if previous else 0
                result[term]={"term":term,"group":group,"average":average,"recent":recent,
                              "previous":previous,"change_pct":change,"points":len(vals),
                              "explore_url":"https://trends.google.com/trends/explore?geo=TW&q="+quote(term)}
            batches.append({"group":group,"status":"ok","method":"pytrends","terms":terms})
            done=True
        except Exception as e:
            errors.append(group+" pytrends: "+type(e).__name__+": "+str(e))
        if not done:
            try:
                direct=_direct_trends(terms,group)
                result.update(direct)
                batches.append({"group":group,"status":"ok","method":"direct-trends","terms":terms})
                done=True
            except Exception as e:
                errors.append(group+" direct: "+type(e).__name__+": "+str(e))
                batches.append({"group":group,"status":"error","terms":terms,"error":str(e)})
    return {"available":bool(result),"fetched_at":datetime.now(timezone.utc).isoformat(),
            "keywords":result,"batches":batches,
            "error":"；".join(errors) if errors else None,
            "source_note":"Google Trends 網站資料；pytrends 失敗時改用 Trends web widget endpoint"}


def main():
    OUT.parent.mkdir(exist_ok=True)
    old={}
    try: old=json.loads(OUT.read_text(encoding="utf-8"))
    except Exception: pass
    rows,n=sources() and calculate()
    site_rows,source_count=rows,n
    gt=trends()
    by={x["term"]:x for x in site_rows}
    for term,x in gt.get("keywords",{}).items():
        x["site_score"]=by.get(term,{"score":0})["score"]
        x["opportunity"]=round(max(0,min(100,x["average"]*.55+(100-x["site_score"])*.45)),1)
    opp=sorted([{"term":x["term"],"group":x["group"],"google_average":x["average"],"change_pct":x["change_pct"],"site_score":x["site_score"],"opportunity":x["opportunity"]} for x in gt.get("keywords",{}).values() if x.get("average",0)>=10 and x.get("site_score",0)<=60],key=lambda x:(x["opportunity"],x["change_pct"]),reverse=True)
    week=datetime.now(timezone.utc).date().isoformat()
    hist=[h for h in old.get("history",[]) if h.get("week")!=week]
    hist=(hist+[{"week":week,"keywords":[{"term":x["term"],"score":x["score"]} for x in site_rows]}])[-12:]
    data={"schema_version":"2.0","type":"seo_geo_trend","generated_at":datetime.now(timezone.utc).isoformat(),"corpus":{"sources":source_count,"public_pages":sum((ROOT/x).exists() for x in PUBLIC),"ai_knowledge_files":sum((ROOT/x).exists() for x in AI)},"groups":TERMS,"keywords":site_rows,"google_trends":gt,"google_opportunities":opp,"history":hist,"recommendations":[{"term":x["term"],"action":"補充直接回答搜尋問題的正文、FAQ、H2與內部連結。"} for x in sorted(site_rows,key=lambda z:z["score"]) if x["score"]<35][:12],"method":{"site":"公開頁面＋AI/GEO可讀檔；每一來源單詞最多計20次","google":"Google Trends Taiwan Web Search，12個月，分三批比較","opportunity":"Trends 55% + 內容缺口45%；不代表排名預測"}}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"sources":source_count,"public_pages":data["corpus"]["public_pages"],"ai_knowledge_files":data["corpus"]["ai_knowledge_files"],"google_trends":gt["available"],"google_keywords":len(gt["keywords"])},ensure_ascii=False))
if __name__=="__main__": main()
