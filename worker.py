import os
import json
import time
import hashlib
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone

# ==============================================================================
# NATIVAGAS CLOUD WORKER — VERSÃO 100% GRATUITA (SEM RAPIDAPI)
# Busca vagas reais em feeds RSS/APIs abertas + indexação pública do LinkedIn
# Calcula % Match com o perfil da Natália Cristine e envia no WhatsApp
# ==============================================================================

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "5511991226615")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
MIN_MATCH_ALERT = int(os.getenv("MIN_MATCH_ALERT", "72"))
SENT_CACHE_FILE = "sent_jobs.json"

CANDIDATE_PROFILE = {
    "name": "Natália Cristine",
    "search_queries": [
        "site:linkedin.com/jobs Analista de Logistica WMS",
        "site:linkedin.com/jobs Key User WMS",
        "site:linkedin.com/jobs Torre de Controle Logistica",
        "site:linkedin.com/jobs Analista MIS Power BI SQL",
        "site:linkedin.com/jobs Analista Planejamento Logistico remoto",
        "site:linkedin.com/jobs Analista Comercio Exterior"
    ],
    "core_skills": {
        "wms": 20, "key user": 20, "torre de controle": 18, "logistica": 16,
        "logística": 16, "power bi": 15, "sql": 15, "vba": 14, "excel": 12,
        "erp": 12, "roteirizacao": 14, "roteirização": 14, "inventario": 12,
        "inventário": 12, "kpi": 12, "sla": 12, "bpmn": 12, "pop": 10,
        "uat": 14, "faturamento": 10, "ct-e": 12, "comex": 12, "awb": 10,
        "control desk": 14, "forecast": 12, "armazenagem": 12, "picking": 10,
        "putaway": 10, "alteryx": 12, "oracle": 12, "sql server": 14,
        "remoto": 10, "home office": 10, "remote": 10, "supply chain": 12
    }
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

def load_sent_jobs():
    if os.path.exists(SENT_CACHE_FILE):
        try:
            with open(SENT_CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_jobs(job_ids):
    with open(SENT_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(job_ids)[-800:], f, ensure_ascii=False, indent=2)

def calculate_match(title: str, description: str) -> tuple[int, list[str]]:
    text = f"{title} {description}".lower()
    score = 35
    matched_tags = []
    for skill, weight in CANDIDATE_PROFILE["core_skills"].items():
        if skill in text:
            score += weight
            tag = skill.upper()
            if tag not in matched_tags:
                matched_tags.append(tag)
    return min(score, 99), matched_tags[:6]

def fetch_bing_linkedin_rss(query: str) -> list[dict]:
    """Lê feed RSS público do Bing indexando vagas recentes do LinkedIn (100% gratuito)"""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded}&format=rss"
    results = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if "linkedin.com" in link and title:
                results.append({
                    "title": title.replace(" | LinkedIn", ""),
                    "link": link,
                    "description": desc,
                    "source": "LinkedIn (Indexado)"
                })
    except Exception as e:
        print(f"[Aviso RSS Bing] {query}: {e}")
    return results

def fetch_remotive_api() -> list[dict]:
    """API pública e gratuita da Remotive para vagas remotas"""
    results = []
    for kw in ["logistics", "supply chain", "data analyst", "operations"]:
        try:
            url = f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(kw)}&limit=10"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            data = resp.json().get("jobs", [])
            for j in data:
                loc = (j.get("candidate_required_location") or "").lower()
                if any(x in loc for x in ["worldwide", "anywhere", "latam", "latin america", "brazil", "americas"]):
                    results.append({
                        "title": f"{j.get('title')} — {j.get('company_name')}",
                        "link": j.get("url"),
                        "description": f"{j.get('category', '')} {j.get('candidate_required_location', '')} {j.get('salary', '')}",
                        "source": "Remotive 100% Remoto"
                    })
        except Exception as e:
            print(f"[Aviso Remotive] {kw}: {e}")
    return results

def send_whatsapp_callmebot(message: str):
    if not CALLMEBOT_APIKEY:
        print("[SIMULAÇÃO WHATSAPP - Configure CALLMEBOT_APIKEY nos Secrets]
" + message)
        return
    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": WHATSAPP_NUMBER,
        "text": message,
        "apikey": CALLMEBOT_APIKEY
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        print(f"[WhatsApp Enviado] HTTP {r.status_code}")
    except Exception as e:
        print(f"[Erro envio WhatsApp] {e}")

def run_cycle():
    print(f"=== NATIVAGAS Radar Gratuito: {datetime.now(timezone.utc).isoformat()} ===")
    sent_jobs = load_sent_jobs()
    candidates = []

    for q in CANDIDATE_PROFILE["search_queries"]:
        candidates.extend(fetch_bing_linkedin_rss(q))
        time.sleep(1)

    candidates.extend(fetch_remotive_api())

    new_alerts = 0
    for job in candidates:
        link = job.get("link", "")
        if not link:
            continue
        job_id = hashlib.md5(link.split("?")[0].encode("utf-8")).hexdigest()
        if job_id in sent_jobs:
            continue

        title = job.get("title", "Vaga Compatível")
        desc = job.get("description", "")
        source = job.get("source", "Web")
        match_pct, tags = calculate_match(title, desc)
        sent_jobs.add(job_id)

        if match_pct >= MIN_MATCH_ALERT:
            tags_str = ", ".join(tags) if tags else "Logística / Processos / Dados"
            msg = (
                f"🚀 *NATIVAGAS — {match_pct}% MATCH*

"
                f"💼 *{title}*
"
                f"📡 Fonte: {source}
"
                f"🎯 *Palavras-chave do seu CV:* {tags_str}

"
                f"🔗 *Acessar vaga:* {link}"
            )
            send_whatsapp_callmebot(msg)
            new_alerts += 1
            time.sleep(3)

    save_sent_jobs(sent_jobs)
    print(f"=== Varredura concluída. Alertas enviados: {new_alerts} ===")

if __name__ == "__main__":
    run_cycle()
