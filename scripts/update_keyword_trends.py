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

def trends():
    try:
        from pytrends.request import TrendReq
    except Exception as e:
        return {"available":False,"error":"pytrends 未安裝："+str(e),"keywords":{},"batches":[]}
    result={}; batches=[]; errors=[]
    for group,terms in [
        ("修行與禪修",["禪修","修行","修道","冥想","靈性"]),
        ("宗教與靜坐",["打坐","靜坐","佛教","道教","宗教"]),
        ("中天與地區",["中天法門","中天法門台南","中天法門東山","台南禪修","東山禪修"])]:
        try:
            py=TrendReq(hl="zh-TW",tz=480,retries=2,backoff_factor=0.5)
            py.build_payload(terms,cat=0,timeframe="today 12-m",geo="TW",gprop="")
            interest=py.interest_over_time()
            av=py.interest_over_time().mean(numeric_only=True).to_dict()
            for term in terms:
                vals=[float(x) for x in interest[term].tolist()] if term in interest else []
                recent=sum(vals[-4:])/len(vals[-4:]) if vals[-4:] else 0
                previous=sum(vals[-8:-4])/len(vals[-8:-4]) if len(vals)>=8 else 0
                average=float(av.get(term,0) or 0)
                change=((recent-previous)/previous*100) if previous else 0
                result[term]={"term":term,"group":group,"average":average,"recent":recent,"previous":previous,"change_pct":change,"points":len(vals),"explore_url":"https://trends.google.com/trends/explore?geo=TW&q="+quote(term)}
            batches.append({"group":group,"status":"ok","terms":terms})
        except Exception as e:
            errors.append(group+": "+type(e).__name__+": "+str(e))
            batches.append({"group":group,"status":"error","terms":terms,"error":str(e)})
    return {"available":bool(result),"fetched_at":datetime.now(timezone.utc).isoformat(),"keywords":result,"batches":batches,"error":"；".join(errors) if errors else None}

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
