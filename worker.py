import os
import json
import time
import hashlib
import requests
from datetime import datetime, timezone

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "5511959074897")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
MIN_MATCH_ALERT = int(os.getenv("MIN_MATCH_ALERT", "65"))
SENT_CACHE_FILE = "sent_jobs.json"

CANDIDATE_PROFILE = {
    "name": "Natália Cristine",
    "core_skills": {
        "wms": 22, "key user": 22, "torre de controle": 20, "logistica": 18,
        "logística": 18, "logistics": 18, "supply chain": 18, "operations": 14,
        "power bi": 16, "sql": 16, "vba": 14, "excel": 12, "erp": 14,
        "roteirizacao": 15, "inventario": 14, "inventory": 14, "kpi": 12,
        "sla": 12, "bpmn": 12, "uat": 14, "comex": 14, "freight": 14,
        "forecast": 12, "warehouse": 15, "data analyst": 14, "bi": 12,
        "remoto": 10, "home office": 10, "remote": 10, "latam": 10, "brazil": 12
    }
}

HEADERS = {
    "User-Agent": "NATIVAGAS-Radar/2.0 (https://github.com)"
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
    score = 42
    matched_tags = []
    for skill, weight in CANDIDATE_PROFILE["core_skills"].items():
        if skill in text:
            score += weight
            tag = skill.upper()
            if tag not in matched_tags:
                matched_tags.append(tag)
    return min(score, 99), matched_tags[:6]

def fetch_remotive_jobs():
    results = []
    for cat in ["data", "business", "all-others"]:
        try:
            url = f"https://remotive.com/api/remote-jobs?category={cat}&limit=25"
            resp = requests.get(url, headers=HEADERS, timeout=20)
            for j in resp.json().get("jobs", []):
                title = j.get("title", "")
                company = j.get("company_name", "Empresa Remota")
                loc = j.get("candidate_required_location", "Worldwide")
                desc = f"{title} {j.get('category', '')} {loc} {' '.join(j.get('tags', []))}"
                if any(k in desc.lower() for k in ["logistic", "supply", "warehouse", "erp", "power bi", "sql", "operations", "data analyst", "inventory", "freight"]):
                    results.append({
                        "company": company,
                        "title": title,
                        "location": loc,
                        "link": j.get("url"),
                        "description": desc,
                        "source": "Remotive (100% Remoto)"
                    })
        except Exception as e:
            print(f"[Erro Remotive {cat}] {e}")
    return results

def fetch_himalayas_jobs():
    results = []
    try:
        url = "https://himalayas.app/jobs/api?limit=40"
        resp = requests.get(url, headers=HEADERS, timeout=20)
        for j in resp.json().get("jobs", []):
            title = j.get("title", "")
            company = j.get("companyName", "Empresa Global")
            excerpt = j.get("excerpt", "")
            full_text = f"{title} {excerpt}".lower()
            if any(k in full_text for k in ["logistic", "supply", "warehouse", "erp", "power bi", "sql", "operations", "data analyst", "inventory", "freight"]):
                results.append({
                    "company": company,
                    "title": title,
                    "location": "Remoto Global / LATAM",
                    "link": j.get("applicationLink") or f"https://himalayas.app/jobs/{j.get('slug', '')}",
                    "description": full_text,
                    "source": "Himalayas Remote"
                })
    except Exception as e:
        print(f"[Erro Himalayas] {e}")
    return results

def fetch_jobicy_jobs():
    results = []
    for tag in ["logistics", "supply-chain", "data-analyst", "operations"]:
        try:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=15&tag={tag}"
            resp = requests.get(url, headers=HEADERS, timeout=20)
            for j in resp.json().get("jobs", []):
                results.append({
                    "company": j.get("companyName", "Empresa Remota"),
                    "title": j.get("jobTitle", "Vaga Remota"),
                    "location": j.get("jobGeo", "Anywhere"),
                    "link": j.get("url"),
                    "description": f"{j.get('jobTitle', '')} {j.get('jobIndustry', '')} {j.get('jobExcerpt', '')}",
                    "source": "Jobicy 100% Remoto"
                })
        except Exception as e:
            print(f"[Erro Jobicy {tag}] {e}")
    return results

def send_whatsapp_callmebot(message):
    if not CALLMEBOT_APIKEY:
        print("[AVISO] CALLMEBOT_APIKEY vazia nos Secrets! Configure em Settings > Secrets.")
        print(message)
        return False
    url = "https://api.callmebot.com/whatsapp.php"
    params = {
        "phone": WHATSAPP_NUMBER,
        "text": message,
        "apikey": CALLMEBOT_APIKEY
    }
    try:
        r = requests.get(url, params=params, timeout=25)
        print(f"[CallMeBot Resposta] HTTP {r.status_code} | {r.text[:120]}")
        return r.status_code == 200
    except Exception as e:
        print(f"[Erro envio WhatsApp] {e}")
        return False

def run_cycle():
    print(f"=== NATIVAGAS Radar Multi-Fontes: {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Destino WhatsApp: {WHATSAPP_NUMBER} | APIKey configurada: {'SIM' if CALLMEBOT_APIKEY else 'NÃO'}")

    sent_jobs = load_sent_jobs()
    first_run = len(sent_jobs) == 0

    candidates = []
    candidates.extend(fetch_remotive_jobs())
    candidates.extend(fetch_himalayas_jobs())
    candidates.extend(fetch_jobicy_jobs())
    print(f"Total de vagas brutas coletadas nas APIs: {len(candidates)}")

    if first_run:
        send_whatsapp_callmebot(
            "✅ *NATIVAGAS Conectado!*\n"
            "Seu radar automático na nuvem está ativo e monitorando vagas 100% remotas compatíveis com o perfil da Natália Cristine."
        )
        time.sleep(3)

    new_alerts = 0
    for job in candidates:
        link = job.get("link", "")
        if not link:
            continue
        job_id = hashlib.md5(link.split("?")[0].encode("utf-8")).hexdigest()
        if job_id in sent_jobs:
            continue

        company = job.get("company", "Empresa Remota")
        title = job.get("title", "Vaga Compatível")
        loc = job.get("location", "100% Remoto")
        desc = job.get("description", "")
        source = job.get("source", "Remoto")
        match_pct, tags = calculate_match(f"{company} {title}", desc)
        sent_jobs.add(job_id)

        if match_pct >= MIN_MATCH_ALERT and new_alerts < 5:
            tags_str = ", ".join(tags) if tags else "Logística / Operações / Dados"
            msg = (
                f"🚀 *NATIVAGAS — {match_pct}% MATCH*\n\n"
                f"🏢 *Empresa:* {company}\n"
                f"💼 *Vaga:* {title}\n"
                f"📍 *Local:* {loc}\n"
                f"📡 *Fonte:* {source}\n"
                f"🎯 *Skills:* {tags_str}\n\n"
                f"🔗 *Candidatar-se:* {link}"
            )
            if send_whatsapp_callmebot(msg):
                new_alerts += 1
                time.sleep(4)

    save_sent_jobs(sent_jobs)
    print(f"=== Varredura concluída. Alertas enviados nesta rodada: {new_alerts} ===")

if __name__ == "__main__":
    run_cycle()
