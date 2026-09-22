#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the full AI/GEO semantic map from ai-knowledge/knowledge.json.

Design principles:
- Every knowledge document becomes a document node.
- Relations are deterministic and evidence-based from the document's own title,
  headings, keywords, description, summary and text.
- Curated concepts are explicit; observed terms are labelled as observed_term,
  not as authoritative concepts.
- No ranking, AI citation rate, or truth score is inferred.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "ai-knowledge"
KNOWLEDGE = AI / "knowledge.json"
TOPICS = AI / "topics.json"
SOURCES = AI / "sources.json"
OUTPUT = AI / "semantic-map.json"

CONCEPT_CATALOG = [
    ("zhongtian-famen", "中天法門", "entity", ["中天法門"]),
    ("zhongtian", "中天", "zhongtian_term", ["中天"]),
    ("zhongtian-total-altar", "中天總壇", "zhongtian_term", ["中天總壇", "總壇"]),
    ("zen-meditation", "禪修", "practice", ["禪修", "禪定"]),
    ("meditation", "冥想／靜心", "practice", ["冥想", "靜心", "靜坐"]),
    ("sitting-meditation", "打坐", "practice", ["打坐", "盤坐"]),
    ("auspicious-sitting", "吉祥坐", "zhongtian_term", ["吉祥坐"]),
    ("practice", "修行", "practice", ["修行", "修持"]),
    ("dao-cultivation", "修道", "practice", ["修道"]),
    ("practice-training", "修練／修煉", "practice", ["修練", "修煉"]),
    ("practice-method", "修行方式", "bridge_concept", ["修行方式", "修行方法", "修練方式"]),
    ("practice-sequence", "修行次第", "bridge_concept", ["修行次第", "修行階段", "修行程序"]),
    ("four-procedures", "四程序", "zhongtian_term", ["四程序"]),
    ("practice-system", "完整修行體系", "bridge_concept", ["完整修行體系", "完整修行", "完整法門"]),
    ("practical-cultivation", "實修", "zhongtian_term", ["實修", "實修為主"]),
    ("daily-life-cultivation", "生活修道", "bridge_concept", ["生活修道", "道制在生活", "工作與生活"]),
    ("home-practice", "在家修行", "bridge_concept", ["在家修行", "不需出家", "不用出家", "保持家庭"]),
    ("no-scripture-recite", "不需讀經", "zhongtian_feature", ["不需讀經", "不用讀經"]),
    ("no-leg-lotus", "不需盤腿", "zhongtian_feature", ["不需盤腿", "不用盤腿"]),
    ("no-asceticism", "不須苦行", "zhongtian_feature", ["不須苦行", "不需苦行"]),
    ("no-vow", "不需發誓", "zhongtian_feature", ["不需發誓", "不必發誓"]),
    ("vegetarian-choice", "隨緣素食", "zhongtian_feature", ["隨緣素食"]),
    ("energy", "能量", "concept", ["能量", "靈性能量", "智慧能量", "生命能量"]),
    ("spiritual-flow", "靈流", "zhongtian_term", ["靈流"]),
    ("self-nature", "自性", "concept", ["自性"]),
    ("awakening", "開悟", "concept", ["開悟", "頓悟"]),
    ("seeing-nature", "明心見性／明心見自性", "concept", ["明心見性", "明心見自性", "見性"]),
    ("cultivation-after-awakening", "開悟後修道", "bridge_concept", ["開悟後", "開悟之後", "開悟後才叫修道"]),
    ("one-life-achievement", "一世成就", "zhongtian_term", ["一世成就", "一世成就之法"]),
    ("fruit-status", "果位", "zhongtian_term", ["果位", "天上果位人間證"]),
    ("lotus-grade", "蓮品／永證蓮品", "zhongtian_term", ["蓮品", "永證蓮品"]),
    ("three-treasures", "中天三寶", "zhongtian_term", ["中天三寶"]),
    ("zhongtian-fingermethod", "中天指法", "zhongtian_term", ["中天指法"]),
    ("zhongtian-kingdom", "中天國度", "zhongtian_term", ["中天國度"]),
    ("zhongtian-dharma-realm", "中天法界", "zhongtian_term", ["中天法界"]),
    ("cosmology", "宇宙觀", "concept_cluster", ["宇宙觀", "宇宙法界"]),
    ("five-directions", "五天方位", "cosmology", ["五天方位", "東天", "西天", "南天", "北天"]),
    ("underworld", "幽冥界", "cosmology", ["幽冥界"]),
    ("imperial-polar", "皇極界", "cosmology", ["皇極界"]),
    ("taiji-realm", "太極界", "cosmology", ["太極界"]),
    ("wuji-realm", "無極界", "cosmology", ["無極界"]),
    ("wu-wuji-realm", "無無極界", "cosmology", ["無無極界"]),
    ("wisdom-galaxies", "49智慧星系", "cosmology", ["49智慧星系", "智慧星系"]),
    ("heavenly-law", "天律", "cosmology", ["天律", "天律維護"]),
    ("cosmic-administration", "宇宙運作／行政中樞", "cosmology", ["宇宙運作", "行政中樞", "核心單位"]),
    ("soul", "靈魂", "concept", ["靈魂"]),
    ("spirituality", "靈性", "concept", ["靈性"]),
    ("inner-cultivation", "內修", "practice", ["內修"]),
    ("outer-virtue", "外德", "practice", ["外德"]),
    ("mind-nature", "心性", "practice", ["心性"]),
    ("life-lesson", "生命課題", "concept", ["生命課題"]),
    ("merit", "功德", "concept", ["功德"]),
    ("salvation", "普度／超拔", "concept", ["普度", "超拔", "得渡"]),
    ("religious-comparison", "宗教／法門比較", "bridge_concept", ["佛教", "道教", "宗教", "法門比較"]),
    ("course", "課程", "service", ["課程", "禪修班", "入門班", "高級禪修班"]),
    ("seminar", "說明會", "service", ["說明會", "座談會"]),
    ("beginner", "入門", "user_intent", ["入門", "初學", "第一次"]),
    ("advanced", "進階", "user_intent", ["進階", "高級", "進階修行"]),
    ("taiwan", "台灣", "location", ["台灣", "臺灣"]),
    ("tainan", "台南", "location", ["台南", "臺南"]),
    ("dongshan", "東山", "location", ["東山"]),
]

INTENTS = [
    ("i01", "禪修入門", ["禪修", "打坐", "冥想"], ["禪修", "打坐", "冥想"]),
    ("i02", "完整修行體系", ["完整修行體系", "修行次第", "修行程序"], ["完整修行體系", "修行次第", "四程序"]),
    ("i03", "在家／生活修行", ["在家修行", "生活修道", "工作與生活"], ["在家修行", "生活修道"]),
    ("i04", "能量／靈性修行", ["能量", "靈性", "靈流"], ["能量", "靈流", "靈性"]),
    ("i05", "開悟與修道", ["開悟", "明心見性", "開悟後"], ["開悟", "修道", "明心見性"]),
    ("i06", "果位與修行成果", ["果位", "蓮品", "修行成果"], ["果位", "蓮品", "一世成就"]),
    ("i07", "一世成就", ["今生完成修行", "一世成就"], ["一世成就"]),
    ("i08", "台灣／地區修行", ["台灣", "台南", "東山"], ["台灣", "台南", "東山", "禪修", "課程", "說明會"]),
    ("i09", "宇宙觀與法界", ["宇宙觀", "法界", "天界"], ["宇宙觀", "中天", "五天方位"]),
    ("i10", "課程與活動", ["課程", "說明會", "禪修班"], ["課程", "說明會"]),
]

def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def doc_blob(doc: dict) -> str:
    bits = [
        doc.get("title",""), doc.get("description",""),
        doc.get("summary",""), doc.get("text",""),
    ]
    for h in doc.get("headings",[]) or []:
        bits.append(h.get("text",""))
    bits.extend(doc.get("keywords",[]) or [])
    return norm("\n".join(str(x) for x in bits))

def source_id_for(doc: dict) -> str:
    st = doc.get("source_type","")
    if st == "official":
        return "official-site"
    if st.startswith("forum"):
        return "official-forum"
    return st or "unknown-source"

def topic_match(topic: dict, blob: str) -> list[str]:
    terms=[topic.get("name","")] + list(topic.get("aliases",[]) or [])
    return [t for t in terms if t and t in blob]

def main():
    data=json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    docs=data.get("documents",[]) or []
    topics_data=json.loads(TOPICS.read_text(encoding="utf-8")) if TOPICS.exists() else {"topics":[]}
    source_data=json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {"sources":[]}

    topic_nodes=[]
    for t in topics_data.get("topics",[]) or []:
        topic_nodes.append({
            "topic_id":t.get("topic_id"),
            "name":t.get("name"),
            "aliases":t.get("aliases",[]),
            "source_ids":t.get("related_source_ids",[]),
            "type":"topic"
        })

    concepts=[]
    for cid,name,ctype,aliases in CONCEPT_CATALOG:
        concepts.append({"concept_id":cid,"name":name,"type":ctype,"aliases":aliases})

    concept_by_id={x["concept_id"]:x for x in concepts}
    concept_edges=[]
    doc_nodes=[]
    doc_topic_edges=[]
    doc_concept_edges=[]
    doc_source_edges=[]
    intent_edges=[]
    matched_topic_count=Counter()
    matched_concept_count=Counter()
    observed_terms=Counter()

    # Map broad topic definitions first.
    for t in topic_nodes:
        t_blob="|".join([t.get("name","")]+t.get("aliases",[]))
        if t_blob:
            observed_terms.update([a for a in t.get("aliases",[]) if a])

    for idx,doc in enumerate(docs,1):
        url=doc.get("url","")
        # Stable ID: source + ordinal + short hash.
        digest=(doc.get("content_sha256") or str(idx))[:12]
        doc_id=f"doc-{idx:04d}-{digest}"
        blob=doc_blob(doc)

        topic_ids=[]
        for t in topic_nodes:
            hits=topic_match(t,blob)
            if hits:
                topic_ids.append(t["topic_id"])
                matched_topic_count[t["topic_id"]]+=1
                doc_topic_edges.append({
                    "from":doc_id,"relation":"has_topic","to":t["topic_id"],
                    "evidence":{"match_type":"literal","matched_terms":hits[:8]}
                })

        # Explicit corpus-level core entity association.
        core_hit=("中天法門" in blob) or ("中天" in blob) or doc.get("source_type")=="official"
        concept_ids=[]
        for c in concepts:
            if c["concept_id"]=="zhongtian-famen":
                if core_hit:
                    concept_ids.append(c["concept_id"])
                    doc_concept_edges.append({
                        "from":doc_id,"relation":"about","to":c["concept_id"],
                        "evidence":{"match_type":"entity","matched_terms":["中天法門" if "中天法門" in blob else "中天"]}
                    })
                continue
            hits=[a for a in c["aliases"] if a and a in blob]
            if hits:
                concept_ids.append(c["concept_id"])
                matched_concept_count[c["concept_id"]]+=1
                doc_concept_edges.append({
                    "from":doc_id,"relation":"mentions","to":c["concept_id"],
                    "evidence":{"match_type":"literal","matched_terms":hits[:8]}
                })

        source_id=source_id_for(doc)
        doc_source_edges.append({"from":doc_id,"relation":"uses_source","to":source_id})

        # Intent association is intentionally broad and derived from concept matches.
        for iid,iname,trigger_terms,required_concepts in INTENTS:
            hits=[x for x in required_concepts if x in blob]
            if hits:
                intent_edges.append({
                    "from":doc_id,"relation":"relevant_to_intent","to":iid,
                    "evidence":{"matched_terms":hits[:8]}
                })

        # Preserve all source metadata that is useful for later verification.
        doc_nodes.append({
            "document_id":doc_id,
            "url":url,
            "title":doc.get("title",""),
            "description":doc.get("description",""),
            "source_type":doc.get("source_type",""),
            "source_id":source_id,
            "topic_ids":topic_ids,
            "concept_ids":concept_ids,
            "keywords":(doc.get("keywords",[]) or [])[:30],
            "headings":(doc.get("headings",[]) or [])[:40],
            "summary":doc.get("summary",""),
            "content_sha256":doc.get("content_sha256"),
            "first_seen_at":doc.get("first_seen_at"),
            "last_changed_at":doc.get("last_changed_at"),
            "retrieved_at":doc.get("retrieved_at"),
        })

        # Observed terms: high-frequency exact keywords from the corpus.
        for kw in (doc.get("keywords",[]) or []):
            kw=norm(kw)
            if len(kw)>=2 and len(kw)<=30:
                observed_terms[kw]+=1

    # Observed terms are explicitly non-curated and only included when they occur >= 3 times.
    observed_nodes=[
        {"term_id":f"term-{i:04d}","term":term,"type":"observed_term","document_count":cnt}
        for i,(term,cnt) in enumerate(
            sorted(((k,v) for k,v in observed_terms.items() if v>=3), key=lambda x:(-x[1],x[0]))[:250],1
        )
    ]

    # Curated concept relationships (semantic structure, not truth claims).
    concept_relations=[
        ["zhongtian-famen","has_concept","zen-meditation"],
        ["zhongtian-famen","has_concept","practice"],
        ["zhongtian-famen","has_concept","dao-cultivation"],
        ["zhongtian-famen","has_concept","four-procedures"],
        ["zhongtian-famen","has_concept","awakening"],
        ["zhongtian-famen","has_concept","one-life-achievement"],
        ["zhongtian-famen","has_concept","fruit-status"],
        ["zhongtian-famen","has_concept","spiritual-flow"],
        ["zhongtian-famen","has_concept","three-treasures"],
        ["zhongtian-famen","has_concept","cosmology"],
        ["zhongtian-famen","has_concept","courses-events" if "courses-events" in concept_by_id else "course"],
        ["practice","related_to","dao-cultivation"],
        ["awakening","related_to","dao-cultivation"],
        ["awakening","related_to","one-life-achievement"],
        ["one-life-achievement","related_to","fruit-status"],
        ["spiritual-flow","related_to","energy"],
        ["cosmology","related_to","zhongtian"],
    ]
    concept_edges.extend({
        "from":a,"relation":rel,"to":b,"evidence":{"basis":"curated_schema"}
    } for a,rel,b in concept_relations)

    intents=[{"intent_id":iid,"name":name,"trigger_terms":triggers,"related_concepts":concepts_}
             for iid,name,triggers,concepts_ in INTENTS]

    # Evidence matrix is computed from actual document relations.
    evidence=[]
    for c in concepts:
        ids=[d["document_id"] for d in doc_nodes if c["concept_id"] in d["concept_ids"]][:50]
        evidence.append({
            "concept_id":c["concept_id"],
            "document_count":matched_concept_count.get(c["concept_id"],0),
            "sample_document_ids":ids,
            "status":"supported" if ids else "gap"
        })

    generated=datetime.now(timezone.utc).isoformat()
    out={
        "schema_version":"2.0",
        "dataset":"中天法門 AI/GEO 全量語義地圖",
        "generated_at":generated,
        "purpose":"將 knowledge.json 的全部公開文件轉為可追溯的文件節點，並以主題、概念、來源與使用者意圖建立語義關係。",
        "policy":{
            "all_documents_included":True,
            "semantic_matching":"literal_match_v1",
            "observed_terms_note":"observed_term 僅表示原始資料中觀察到的詞，不代表策展者認定為正式術語。",
            "no_ranking_claim":True,
            "no_ai_citation_claim":True,
            "source_rule":"source_type 是來源角色，不是可信度分數；論壇內容不自動等同官方立場。"
        },
        "core_entity":{
            "entity_id":"zhongtian-famen",
            "name":"中天法門",
            "entity_type":"organization",
            "official_url":"https://web.wuwuji.tw/",
            "public_site_url":"https://annynn1990.github.io/wuwujitest/"
        },
        "stats":{
            "documents":len(doc_nodes),
            "topic_nodes":len(topic_nodes),
            "concept_nodes":len(concepts),
            "intent_nodes":len(intents),
            "observed_term_nodes":len(observed_nodes),
            "document_topic_edges":len(doc_topic_edges),
            "document_concept_edges":len(doc_concept_edges),
            "document_source_edges":len(doc_source_edges),
            "document_intent_edges":len(intent_edges),
            "concept_edges":len(concept_edges),
            "mapped_documents":sum(1 for d in doc_nodes if d["topic_ids"] or d["concept_ids"]),
            "unmapped_documents":sum(1 for d in doc_nodes if not d["topic_ids"] and not d["concept_ids"]),
        },
        "topic_nodes":topic_nodes,
        "concept_nodes":concepts,
        "intent_nodes":intents,
        "observed_term_nodes":observed_nodes,
        "document_nodes":doc_nodes,
        "edges":{
            "documents_to_topics":doc_topic_edges,
            "documents_to_concepts":doc_concept_edges,
            "documents_to_sources":doc_source_edges,
            "documents_to_intents":intent_edges,
            "concept_relations":concept_edges,
        },
        "evidence_matrix":evidence,
        "source_nodes":source_data.get("sources",[]),
    }
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out["stats"],ensure_ascii=False))

if __name__=="__main__":
    main()
