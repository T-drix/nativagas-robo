import os
import json
import time
import hashlib
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "5511959074897")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
MIN_MATCH_ALERT = int(os.getenv("MIN_MATCH_ALERT", "65"))
SENT_CACHE_FILE = "sent_jobs.json"

CANDIDATE_PROFILE = {
    "name": "Natália Cristine",
    "queries_br": [
        '"vaga" ("WMS" OR "Key User") ("remoto" OR "home office")',
        '"vaga" "Torre de Controle" ("logística" OR "remoto" OR "home office")',
        '"vaga" ("Analista de Logística" OR "Planejamento Logístico") ("remoto" OR "home office")',
        '"vaga" ("Power BI" OR "SQL" OR "MIS") "logística" ("remoto" OR "home office")',
        '"vaga" ("Comércio Exterior" OR "Comex") ("remoto" OR "home office")',
        'site:linkedin.com/jobs ("Logística" OR "WMS" OR "Torre de Controle") "remoto" Brasil',
        'site:gupy.io ("Logística" OR "WMS" OR "Torre de Controle" OR "Power BI") "remoto"'
    ],
    "core_skills": {
        "wms": 22, "key user": 22, "torre de controle": 20, "logistica": 18,
        "logística": 18, "power bi": 16, "sql": 16, "vba": 14, "excel": 12,
        "erp": 14, "roteirizacao": 15, "roteirização": 15, "inventario": 14,
        "inventário": 14, "kpi": 12, "sla": 12, "bpmn": 12, "uat": 14,
        "comex": 14, "comércio exterior": 14, "ct-e": 12, "forecast": 12,
        "armazenagem": 14, "mis": 15, "oracle": 12, "alteryx": 12,
        "remoto": 12, "home office": 12, "brasil": 10
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

def calculate_match(title, description):
    text = f"{title} {description}".lower()
    score = 45
    matched_tags = []
    for skill, weight in CANDIDATE_PROFILE["core_skills"].items():
        if skill in text:
            score += weight
            tag = skill.upper()
            if tag not in matched_tags:
                matched_tags.append(tag)
    return min(score, 99), matched_tags[:6]

def fetch_google_news_br_rss(query):
    # Busca indexada em tempo real no Brasil (último 1 dia)
    encoded = urllib.parse.quote_plus(f"{query} when:1d")
    url = f"https://news.google.com/rss/search?q={encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    results = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            raw_title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source_name = source_el.text.strip() if source_el is not None and source_el.text else "Portal Brasil"

            if raw_title and link:
                # Limpa o sufixo " - Nome do Portal" do título
                clean_title = raw_title.rsplit(" - ", 1)[0].strip()
                results.append({
                    "company": source_name,
                    "title": clean_title,
                    "location": "Brasil • 100% Remoto / Home Office",
                    "link": link,
                    "description": f"{clean_title} {source_name} {pub_date}",
                    "source": f"{source_name} (Brasil)"
                })
    except Exception as e:
        print(f"[Aviso Busca BR] {query}: {e}")
    return results

def send_whatsapp_callmebot(message):
    if not CALLMEBOT_APIKEY:
        print("[AVISO] CALLMEBOT_APIKEY vazia nos Secrets!")
        return False
    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": WHATSAPP_NUMBER,
        "text": message,
        "apikey": CALLMEBOT_APIKEY
    }
    try:
        r = requests.get(url, params=params, timeout=25)
        print(f"[CallMeBot Resposta] HTTP {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"[Erro envio WhatsApp] {e}")
        return False

def run_cycle():
    print(f"=== NATIVAGAS Radar Brasil (100% Português): {datetime.now(timezone.utc).isoformat()} ===")
    sent_jobs = load_sent_jobs()
    candidates = []

    for q in CANDIDATE_PROFILE["queries_br"]:
        candidates.extend(fetch_google_news_br_rss(q))
        time.sleep(1)

    print(f"Total de oportunidades encontradas no Brasil hoje: {len(candidates)}")

    new_alerts = 0
    for job in candidates:
        link = job.get("link", "")
        title = job.get("title", "")
        if not link or not title:
            continue
        # Usa hash do título normalizado para evitar duplicadas de portais diferentes
        job_id = hashlib.md5(title.lower().strip().encode("utf-8")).hexdigest()
        if job_id in sent_jobs:
            continue

        company = job.get("company", "Portal de Vagas BR")
        loc = job.get("location", "Brasil • Remoto")
        desc = job.get("description", "")
        source = job.get("source", "Brasil")
        match_pct, tags = calculate_match(title, desc)
        sent_jobs.add(job_id)

        if match_pct >= MIN_MATCH_ALERT and new_alerts < 5:
            tags_str = ", ".join(tags) if tags else "Logística / WMS / Dados"
            msg = (
                f"🇧🇷 *NATIVAGAS — {match_pct}% MATCH*\n\n"
                f"💼 *Vaga:* {title}\n"
                f"🏢 *Portal/Fonte:* {company}\n"
                f"📍 *Local:* {loc}\n"
                f"🎯 *Skills:* {tags_str}\n\n"
                f"🔗 *Acessar vaga:* {link}"
            )
            if send_whatsapp_callmebot(msg):
                new_alerts += 1
                time.sleep(4)

    save_sent_jobs(sent_jobs)
    print(f"=== Varredura Brasil concluída. Alertas enviados: {new_alerts} ===")

if __name__ == "__main__":
    run_cycle()
