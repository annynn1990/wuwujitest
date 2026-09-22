#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re, urllib.request, urllib.error, hashlib
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "ai-knowledge"
OUT = ROOT / "seo-dashboard" / "geo-bot-report.json"
HISTORY = ROOT / "seo-dashboard" / "geo-effect-history.json"
SITE_BASE = "https://annynn1990.github.io/wuwujitest/"

CORE_PAGES = {
    "首頁": "index.html",
    "關於本站": "about.html",
    "禪修": "meditation.html",
    "課程": "course.html",
    "說明會": "seminar.html",
    "FAQ": "faq.html",
}
CORE_CONCEPTS = [
    ("中天法門", ["中天法門"]),
    ("完整修行體系", ["完整修行體系"]),
    ("四程序", ["四程序"]),
    ("一世成就", ["一世成就"]),
    ("靈流", ["靈流"]),
    ("開悟", ["開悟"]),
    ("修道", ["修道"]),
    ("果位", ["果位", "天上果位人間證"]),
    ("中天三寶", ["中天三寶"]),
    ("生活修道", ["生活修道", "道制在生活"]),
    ("宇宙觀", ["宇宙觀"]),
    ("新手入門", ["入門", "第一次", "禪修"]),
]

class HTMLInfo(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.h1 = []
        self.text = []
        self._title = False
        self._h1 = False
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._title = True
        if tag == "h1":
            self._h1 = True
        if tag == "meta" and attrs.get("name","").lower() == "description":
            self.description = attrs.get("content","") or ""
    def handle_endtag(self, tag):
        if tag == "title":
            self._title = False
        if tag == "h1":
            self._h1 = False
    def handle_data(self, data):
        if self._title:
            self.title += data
        if self._h1:
            self.h1.append(data.strip())
        self.text.append(data)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def fetch_text(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Wuwuji-GEO-Bot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode("utf-8", "replace")

def score_entity(pages):
    checks = [
        any("中天法門" in p["title"] for p in pages.values()),
        sum("中天法門" in p["h1"] for p in pages.values()) >= 2,
        sum("中天法門" in p["text"] for p in pages.values()) >= 3,
        (ROOT / "robots.txt").exists(),
        (AI / "knowledge-graph.json").exists(),
    ]
    return round(sum(checks) / len(checks) * 100)

def score_knowledge(knowledge, semantic, manifest):
    n = len(knowledge.get("documents", []))
    expected = int(manifest.get("last_run", {}).get("documents", 0) or n or 1)
    graph_n = int(semantic.get("stats", {}).get("documents", 0) or 0)
    mapped = int(semantic.get("stats", {}).get("mapped_documents", 0) or 0)
    parsed = isinstance(knowledge.get("documents"), list) and n > 0
    parts = [
        100 if parsed else 0,
        min(100, round(n / max(expected, 1) * 100)),
        min(100, round(graph_n / max(n, 1) * 100)),
        min(100, round(mapped / max(n, 1) * 100)),
    ]
    return round(sum(parts)/len(parts)), {"documents":n,"graph_documents":graph_n,"mapped_documents":mapped}

def score_graph(semantic):
    s = semantic.get("stats", {})
    docs = int(s.get("documents", 0) or 0)
    mapped = int(s.get("mapped_documents", 0) or 0)
    concepts = int(s.get("concept_nodes", 0) or 0)
    terms = int(s.get("observed_term_nodes", 0) or 0)
    edges = int(s.get("document_concept_edges", 0) or 0)
    parts = [
        100 if docs >= 1 else 0,
        round(mapped/max(docs,1)*100),
        min(100, round(concepts/60*100)),
        min(100, round(terms/250*100)),
        min(100, round(edges/(docs*3)*100)),
    ]
    return round(sum(parts)/len(parts)), {"concept_nodes":concepts,"observed_terms":terms,"document_concept_edges":edges}

def concept_coverage(pages):
    rows = []
    covered = 0
    for name, terms in CORE_CONCEPTS:
        hits = []
        for label, p in pages.items():
            hay = (p["title"] + " " + " ".join(p["h1"]) + " " + p["text"]).lower()
            if any(t.lower() in hay for t in terms):
                hits.append(label)
        if hits:
            covered += 1
        rows.append({"concept":name,"status":"covered" if hits else "gap","pages":hits})
    return round(covered/len(CORE_CONCEPTS)*100), rows

def score_intent(semantic):
    intents = semantic.get("intent_nodes", []) or []
    valid = sum(1 for x in intents if len(x.get("related_concepts",[]) or []) >= 1)
    return round(valid/max(len(intents),1)*100), {"intent_nodes":len(intents),"mapped_intents":valid}

def score_retrieval(repo_files, blind_db):
    """Score test infrastructure only; real AI effect remains in the separate effect metric."""
    schema_ok=isinstance(blind_db.get("records"),list) and isinstance(blind_db.get("platforms"),list)
    questions=len(blind_db.get("records",[]) or [])
    platforms=len(blind_db.get("platforms",[]) or [])
    slots=sum(1 for q in (blind_db.get("records",[]) or []) for _ in (blind_db.get("platforms",[]) or []))
    tested=sum(
        1 for q in (blind_db.get("records",[]) or [])
        for p in (blind_db.get("platforms",[]) or [])
        if ((q.get("results",{}) or {}).get(p,{}) or {}).get("status")=="tested"
    )
    pending=slots-tested
    db_exists=any(p.as_posix()=="seo-dashboard/geo-blind-tests.json" for p in repo_files)
    parts=[
        100 if db_exists else 0,
        100 if schema_ok and questions>=1 and platforms>=1 else 0,
        100 if slots==int(blind_db.get("planned_platform_slots",0) or slots) else 0,
    ]
    return round(sum(parts)/len(parts)), {
        "test_data_files":1 if db_exists else 0,
        "questions":questions,
        "platforms":platforms,
        "planned_slots":slots,
        "tested_slots":tested,
        "pending_slots":pending
    }

def blind_test_metrics(blind_db):
    """Compute measurable AI/GEO results from tested blind-test slots only."""
    records=blind_db.get("records",[]) or []
    platforms=blind_db.get("platforms",[]) or []
    slot_rows=[]
    for q in records:
        for platform in platforms:
            result=(q.get("results",{}) or {}).get(platform,{}) or {}
            if result.get("status")=="tested":
                slot_rows.append({
                    "question_id":q.get("question_id"),
                    "intent_id":q.get("intent_id"),
                    "platform":platform,
                    "mentioned_entity":bool(result.get("mentioned_entity")),
                    "citation":bool(result.get("citation")),
                    "primary_source_citation":bool(result.get("primary_source_citation")),
                    "concept_recall":bool(result.get("concept_recall")),
                    "factual_accuracy":bool(result.get("factual_accuracy")),
                })

    tested=len(slot_rows)
    slots=len(records)*len(platforms)
    def rate(key):
        return round(sum(1 for x in slot_rows if x[key])/tested*100) if tested else 0

    full_questions={}
    for q in records:
        qid=q.get("question_id")
        per=[]
        for p in platforms:
            x=(q.get("results",{}) or {}).get(p,{}) or {}
            if x.get("status")=="tested":
                per.append((p,x))
        if len(per)==len(platforms) and platforms:
            full_questions[qid]=per

    mention_consistent=round(sum(
        1 for per in full_questions.values()
        if len({bool(x.get("mentioned_entity")) for _,x in per})==1
    )/max(len(full_questions),1)*100) if full_questions else 0

    citation_consistent=round(sum(
        1 for per in full_questions.values()
        if len({bool(x.get("citation")) for _,x in per})==1
    )/max(len(full_questions),1)*100) if full_questions else 0

    complete_consistent=round(sum(
        1 for per in full_questions.values()
        if len({(bool(x.get("mentioned_entity")),bool(x.get("citation"))) for _,x in per})==1
    )/max(len(full_questions),1)*100) if full_questions else 0

    effect=round(
        rate("mentioned_entity")*.25 +
        rate("citation")*.20 +
        rate("primary_source_citation")*.20 +
        rate("concept_recall")*.20 +
        rate("factual_accuracy")*.15
    ) if tested else 0

    per_platform={}
    for p in platforms:
        rows=[x for x in slot_rows if x["platform"]==p]
        n=len(rows)
        per_platform[p]={
            "tested":n,
            "mention_rate":round(sum(x["mentioned_entity"] for x in rows)/n*100) if n else 0,
            "citation_rate":round(sum(x["citation"] for x in rows)/n*100) if n else 0,
            "primary_source_citation_rate":round(sum(x["primary_source_citation"] for x in rows)/n*100) if n else 0,
            "concept_recall":round(sum(x["concept_recall"] for x in rows)/n*100) if n else 0,
            "accuracy":round(sum(x["factual_accuracy"] for x in rows)/n*100) if n else 0,
        }

    return {
        "tested_slots":tested,
        "planned_slots":slots,
        "pending_slots":max(slots-tested,0),
        "coverage_percent":round(tested/max(slots,1)*100),
        "effect_score":effect,
        "mention_rate":rate("mentioned_entity"),
        "citation_rate":rate("citation"),
        "primary_source_citation_rate":rate("primary_source_citation"),
        "concept_recall":rate("concept_recall"),
        "accuracy":rate("factual_accuracy"),
        "fully_tested_questions":len(full_questions),
        "mention_consistency":mention_consistent,
        "citation_consistency":citation_consistent,
        "complete_consistency":complete_consistent,
        "per_platform":per_platform,
    }

def update_effect_history(blind_db, metrics):
    """Append one history point per distinct blind-test dataset state."""
    try:
        raw=(ROOT/"seo-dashboard"/"geo-blind-tests.json").read_bytes()
        dataset_hash=hashlib.sha256(raw).hexdigest()
    except Exception:
        return []
    history=[]
    if HISTORY.exists():
        try:
            existing=load_json(HISTORY)
            history=existing.get("history",[]) or []
        except Exception:
            history=[]
    if history and history[-1].get("dataset_sha256")==dataset_hash:
        return history
    history.append({
        "recorded_at":utc_now(),
        "dataset_sha256":dataset_hash,
        "effect_score":metrics["effect_score"],
        "tested_slots":metrics["tested_slots"],
        "planned_slots":metrics["planned_slots"],
        "mention_rate":metrics["mention_rate"],
        "citation_rate":metrics["citation_rate"],
        "primary_source_citation_rate":metrics["primary_source_citation_rate"],
        "concept_recall":metrics["concept_recall"],
        "accuracy":metrics["accuracy"],
        "mention_consistency":metrics["mention_consistency"],
        "citation_consistency":metrics["citation_consistency"],
        "complete_consistency":metrics["complete_consistency"],
    })
    HISTORY.write_text(json.dumps({
        "schema_version":"1.0",
        "dataset":"中天法門 GEO AI 實測歷史",
        "definition":"只在盲測資料集內容實際變更時新增一筆快照；未測槽位不視為成功或失敗。",
        "history":history
    },ensure_ascii=False,indent=2),encoding="utf-8")
    return history

def score_evidence(semantic, pages):
    """Measure the evidence layer without requiring new pages."""
    ev=semantic.get("evidence_matrix",[]) or []
    total=len(ev)
    with_evidence=sum(1 for x in ev if int(x.get("evidence_count",0) or 0)>0)
    with_primary=sum(1 for x in ev if int(x.get("primary_source_evidence_count",0) or 0)>0)
    evidence_score=round(((with_evidence/max(total,1))*0.7 + (with_primary/max(total,1))*0.3)*100)
    page_score,_=concept_coverage(pages)
    # Evidence carries more weight than page count because the goal is traceability.
    return round(evidence_score*0.7 + page_score*0.3), {
        "concepts_with_evidence":with_evidence,
        "concepts_with_primary_source_evidence":with_primary,
        "concepts_total":total,
        "core_page_coverage":page_score
    }

def scan_site_files():
    rows = []
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or rel.startswith(".github/") or rel.startswith("scripts/"):
            continue
        if p.suffix.lower() not in {".html",".json",".txt",".xml"}:
            continue
        try:
            size = p.stat().st_size
            if size > 25_000_000:
                rows.append({"path":rel,"type":p.suffix.lower(),"size":size,"status":"large-file-skipped"})
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            entry={"path":rel,"type":p.suffix.lower(),"size":size,"status":"ok"}
            if p.suffix.lower()==".json":
                try:
                    json.loads(content); entry["json_valid"]=True
                except Exception as e:
                    entry["json_valid"]=False; entry["error"]=str(e)[:120]
            if p.suffix.lower()==".html":
                parser=HTMLInfo(); parser.feed(content)
                entry["title"]=clean(parser.title)
                entry["h1_count"]=len([h for h in parser.h1 if h])
                entry["description"]=clean(parser.description)
            rows.append(entry)
        except Exception as e:
            rows.append({"path":rel,"status":"error","error":str(e)[:160]})
    return rows

def sitemap_urls():
    path=ROOT/"sitemap.xml"
    if not path.exists(): return []
    try:
        root=ET.fromstring(path.read_text(encoding="utf-8"))
        ns={"sm":"http://www.sitemaps.org/schemas/sitemap/0.9"}
        return [clean(x.text) for x in root.findall(".//sm:loc",ns) if x.text]
    except Exception:
        return []

def live_check(urls):
    out=[]
    for url in urls:
        try:
            status, text = fetch_text(url)
            parser=HTMLInfo(); parser.feed(text)
            out.append({"url":url,"status":status,"ok":200<=status<400,"title":clean(parser.title),"h1_count":len([h for h in parser.h1 if h]),"bytes":len(text.encode("utf-8"))})
        except Exception as e:
            out.append({"url":url,"ok":False,"error":str(e)[:180]})
    return out

def main():
    generated=utc_now()
    knowledge=load_json(AI/"knowledge.json")
    semantic=load_json(AI/"semantic-map.json")
    manifest=load_json(AI/"manifest.json")
    pages={}
    page_paths=[]
    for label, rel in CORE_PAGES.items():
        p=ROOT/rel
        if not p.exists():
            pages[label]={"path":rel,"title":"","h1":[],"text":"","exists":False}
            continue
        parser=HTMLInfo(); parser.feed(p.read_text(encoding="utf-8",errors="replace"))
        pages[label]={"path":rel,"title":clean(parser.title),"h1":[x for x in parser.h1 if x],"description":clean(parser.description),"text":clean(" ".join(parser.text)),"exists":True}
        page_paths.append(rel)

    entity=score_entity(pages)
    knowledge_score, knowledge_meta=score_knowledge(knowledge,semantic,manifest)
    graph_score, graph_meta=score_graph(semantic)
    concept_score, concept_rows=concept_coverage(pages)
    intent_score, intent_meta=score_intent(semantic)
    files=scan_site_files()
    blind_db=load_json(ROOT/"seo-dashboard/geo-blind-tests.json") if (ROOT/"seo-dashboard/geo-blind-tests.json").exists() else {}
    retrieval_score, retrieval_meta=score_retrieval([Path(x["path"]) for x in files], blind_db)
    evidence_score, evidence_meta=score_evidence(semantic,pages)
    blind_metrics=blind_test_metrics(blind_db)
    effect_history=update_effect_history(blind_db,blind_metrics)
    tested_slots=blind_metrics["tested_slots"]
    citation_score=100 if tested_slots>0 else 0
    observability=100 if (ROOT/".github/workflows/geo-bot-report.yml").exists() else 0

    modules=[
        {"id":"entity","name":"Entity 基礎","weight":10,"score":entity,"definition":"核心 Entity 是否能在網站與機器可讀資料中被明確識別。"},
        {"id":"knowledge","name":"公開知識庫","weight":15,"score":knowledge_score,"definition":"知識庫完整性、JSON 可解析性、圖譜文件數一致性與全量映射。"},
        {"id":"semantic","name":"全量語義圖","weight":20,"score":graph_score,"definition":"1,076 份文件與主題、概念、觀察詞之間是否形成可追溯關係。"},
        {"id":"concept-evidence","name":"核心 Concept／Evidence","weight":15,"score":evidence_score,"definition":"核心概念是否同時有現有頁面訊號與可追溯的公開文件證據；不要求每個概念新增頁面。"},
        {"id":"intent","name":"User Intent","weight":10,"score":intent_score,"definition":"使用者意圖是否與概念層形成機器可讀關係。"},
        {"id":"retrieval","name":"GEO 盲測／Retrieval 基礎設施","weight":15,"score":retrieval_score,"definition":"50 題 × 5 平台盲測資料庫與評估欄位是否已具備；實際成效另計。"},
        {"id":"citation","name":"Citation 觀測","weight":10,"score":citation_score,"definition":"是否已有可機器讀取的 AI 引用結果長期資料；尚未建立則為 0。"},
        {"id":"observability","name":"機器人自動監測","weight":5,"score":observability,"definition":"是否有自動掃描、產生報告、更新進度的 workflow。"},
    ]
    total=round(sum(m["score"]*m["weight"] for m in modules)/100)
    files=scan_site_files()
    live=live_check(sitemap_urls())

    invalid_json=[x for x in files if x.get("type")==".json" and x.get("json_valid") is False]
    live_bad=[x for x in live if not x.get("ok")]
    report={
        "schema_version":"1.0",
        "report_type":"geo_robot_site_audit",
        "generated_at":generated,
        "site":SITE_BASE,
        "overall_progress":total,
        "progress_definition":"加權診斷進度，不代表 Google 排名，也不代表 AI 引用機率；各模組依可觀測條件計算。",
        "scan_scope":{
            "repo_public_data_files":len(files),
            "sitemap_urls":len(live),
            "core_pages":len(pages),
            "knowledge_documents":len(knowledge.get("documents",[])),
            "semantic_map_documents":int(semantic.get("stats",{}).get("documents",0) or 0),
        },
        "modules":modules,
        "knowledge":knowledge_meta,
        "semantic":graph_meta,
        "concept_coverage":concept_rows,
        "evidence":evidence_meta,
        "intent":intent_meta,
        "retrieval":retrieval_meta,
        "blind_test":{
            **blind_metrics,
            "questions":retrieval_meta.get("questions",0),
            "platforms":retrieval_meta.get("platforms",0),
            "effect_is_separate":True,
            "history_points":len(effect_history)
        },
        "blind_test_platforms":blind_db.get("platforms",[]),
        "blind_test_records":blind_db.get("records",[]),
        "effect_history":effect_history,
        "live_pages":live,
        "site_inventory_summary":{
            "invalid_json":len(invalid_json),
            "errors":sum(1 for x in files if x.get("status")=="error"),
            "html_files":sum(1 for x in files if x.get("type")==".html"),
            "json_files":sum(1 for x in files if x.get("type")==".json"),
            "txt_files":sum(1 for x in files if x.get("type")==".txt"),
            "xml_files":sum(1 for x in files if x.get("type")==".xml"),
        },
        "flags":[
            *([f"發現 {len(invalid_json)} 個 JSON 無法解析"] if invalid_json else []),
            *([f"Sitemap 有 {len(live_bad)} 個網址無法正常取得"] if live_bad else []),
            *([f"核心 Concept Page 仍缺 {sum(1 for x in concept_rows if x['status']=='gap')} 個概念"] if any(x['status']=='gap' for x in concept_rows) else []),
            *([f"目前有 {retrieval_meta.get('pending_slots',0)} 個盲測槽位尚未測試；這不視為失敗。"] if retrieval_meta.get("pending_slots",0) else []),
            *([ "尚未有 AI Citation 實測結果；AI GEO 實際效果分數維持 0%，不以工程完成度代替。" ] if citation_score==0 else []),
        ],
        "automation":{
            "workflow":"geo-bot-report.yml",
            "trigger":"網站／知識庫相關檔案更新 + 每 6 小時排程",
            "next_action":"重新掃描後覆寫本報告；盲測資料集變更時同步增加一筆 AI GEO 歷史快照。",
            "effect_history_file":"seo-dashboard/geo-effect-history.json"
        }
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"overall_progress":total,"modules":[(m["name"],m["score"]) for m in modules],"flags":report["flags"],"files":len(files),"live_pages":len(live)},ensure_ascii=False))

if __name__=="__main__":
    main()
