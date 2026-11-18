import os
import re
import json
import time
import urllib.parse
import requests
from datetime import datetime, timezone

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
MIN_MATCH_ALERT = int(os.getenv("MIN_MATCH_ALERT", "65"))
SENT_CACHE_FILE = "sent_jobs.json"
CURATED_WEB_FILE = "vagas_curadas.json"

# Perfil privado para os alertas do SEU WhatsApp
ADMIN_PROFILE = {
    "keywords": [
        "WMS", "Key User WMS", "Torre de Controle", "Analista de Logística",
        "Planejamento Logístico", "Power BI Logística", "MIS", "Comércio Exterior"
    ],
    "core_skills": {
        "wms": 22, "key user": 22, "torre de controle": 20, "logistica": 18,
        "logística": 18, "power bi": 16, "sql": 16, "vba": 14, "excel": 12,
        "erp": 14, "roteirizacao": 15, "roteirização": 15, "inventario": 14,
        "inventário": 14, "kpi": 12, "sla": 12, "bpmn": 12, "uat": 14,
        "comex": 14, "comércio exterior": 14, "ct-e": 12, "forecast": 12,
        "armazenagem": 14, "mis": 15, "oracle": 12, "alteryx": 12,
        "remoto": 12, "home office": 12, "teletrabalho": 12
    }
}

# Áreas públicas para alimentar o mural real do app (inclui Bancário, Finanças, Operações, RH, Dados, etc.)
PUBLIC_WEB_QUERIES = [
    {"area": "Bancário & Finanças", "kw": "Bancário"},
    {"area": "Bancário & Finanças", "kw": "Analista Financeiro"},
    {"area": "Operações & Logística", "kw": "Analista Operacional"},
    {"area": "Operações & Logística", "kw": "Analista de Logística"},
    {"area": "Atendimento & Sucesso", "kw": "Customer Success"},
    {"area": "Recursos Humanos", "kw": "Analista de RH"},
    {"area": "Tecnologia & Dados", "kw": "Analista de Dados"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9"
}

def load_json_file(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def fetch_linkedin_guest_jobs(keyword, wt_filter=""):
    encoded_kw = urllib.parse.quote(keyword)
    wt_param = f"&f_WT={wt_filter}" if wt_filter else ""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_kw}&location=Brazil{wt_param}&f_TPR=r86400&start=0"
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return jobs

        cards = re.findall(
            r'data-entity-urn="urn:li:jobPosting:(\d+)".*?base-search-card__title[^>]*>(.*?)</h3>.*?base-search-card__subtitle[^>]*>(.*?)</h4>.*?job-search-card__location[^>]*>(.*?)</span>',
            resp.text,
            flags=re.DOTALL
        )
        for job_id, raw_title, raw_company, raw_loc in cards:
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            company = re.sub(r"<[^>]+>", "", raw_company).strip()
            location = re.sub(r"<[^>]+>", "", raw_loc).strip()
            if job_id and title:
                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company or "Empresa no LinkedIn",
                    "location": location or "Brasil",
                    "link": f"https://www.linkedin.com/jobs/view/{job_id}/"
                })
    except Exception as e:
        print(f"[Erro Search '{keyword}'] {e}")
    return jobs

def inspect_job_details(job_id, title, location_str):
    """Lê a descrição real da vaga, extrai palavras-chave reais e valida a modalidade."""
    detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", resp.text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r"<[^>]+>", " ", no_script)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        text_low = clean_text.lower()
        full_check = f"{title.lower()} {location_str.lower()} {text_low}"

        # Identifica modalidade real lendo a descrição
        modality = "presencial"
        if any(k in full_check for k in ["100% remoto", "trabalho remoto", "modelo remoto", "home office", "teletrabalho", "remoto"]):
            modality = "remoto"
        elif any(k in full_check for k in ["híbrido", "hibrido", "modelo híbrido", "trabalho híbrido"]):
            modality = "hibrido"

        # Identifica contrato real
        contract = "clt"
        if any(k in full_check for k in ["pessoa jurídica", "contratação pj", "regime pj", " pj "]):
            contract = "pj"
        elif "estágio" in full_check or "estagio" in full_check:
            contract = "intern"

        # Verifica idioma e inglês fluente
        pt_markers = ["requisitos", "atividades", "responsabilidades", "experiência", "benefícios", "sobre a vaga"]
        is_portuguese = sum(1 for m in pt_markers if m in text_low) >= 2
        requires_fluent_en = any(eng in full_check for eng in [
            "inglês fluente", "ingles fluente", "inglês avançado", "ingles avancado",
            "fluent english", "advanced english", "bilíngue", "bilingue"
        ])

        return {
            "description_excerpt": clean_text[:450] + ("..." if len(clean_text) > 450 else ""),
            "full_text_low": text_low[:4500],
            "modality": modality,
            "contract": contract,
            "is_portuguese": is_portuguese,
            "requires_fluent_en": requires_fluent_en
        }
    except Exception:
        return None

def calculate_admin_match(title, description):
    text = f"{title} {description}".lower()
    score = 48
    matched_tags = []
    for skill, weight in ADMIN_PROFILE["core_skills"].items():
        if skill in text:
            score += weight
            tag = skill.upper()
            if tag not in matched_tags:
                matched_tags.append(tag)
    return min(score, 99), matched_tags[:6]

def send_whatsapp_callmebot(message):
    if not CALLMEBOT_APIKEY or not WHATSAPP_NUMBER:
        return False
    url = "https://api.callmebot.com/whatsapp.php"
    params = {"phone": WHATSAPP_NUMBER, "text": message, "apikey": CALLMEBOT_APIKEY}
    try:
        r = requests.get(url, params=params, timeout=25)
        return r.status_code == 200
    except Exception:
        return False

def run_cycle():
    print(f"=== NATIVAGAS Curadoria Real (App Web + WhatsApp): {datetime.now(timezone.utc).isoformat()} ===")
    sent_jobs = set(load_json_file(SENT_CACHE_FILE, []))
    existing_web_jobs = load_json_file(CURATED_WEB_FILE, {"jobs": []}).get("jobs", [])
    web_jobs_map = {j["job_id"]: j for j in existing_web_jobs if "job_id" in j}

    # 1. Curadoria para o Mural Público do App (Multi-Áreas)
    for item in PUBLIC_WEB_QUERIES:
        raw_list = fetch_linkedin_guest_jobs(item["kw"], wt_filter="2")[:4]
        for job in raw_list:
            jid = job["job_id"]
            if jid in web_jobs_map:
                continue
            details = inspect_job_details(jid, job["title"], job["location"])
            if not details or not details["is_portuguese"]:
                continue
            web_jobs_map[jid] = {
                "job_id": jid,
                "area": item["area"],
                "title": job["title"],
                "company": job["company"],
                "location": job["location"],
                "modality": details["modality"],
                "contract": details["contract"],
                "link": job["link"],
                "excerpt": details["description_excerpt"],
                "full_text": details["full_text_low"],
                "curated_at": datetime.now(timezone.utc).isoformat()
            }
            time.sleep(1.5)
        time.sleep(1.5)

    # Mantém as 80 vagas reais mais recentes no JSON público do site
    curated_list = list(web_jobs_map.values())[-80:]
    curated_list.reverse()
    save_json_file(CURATED_WEB_FILE, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(curated_list),
        "jobs": curated_list
    })
    print(f"Vagas reais salvas para o App Web: {len(curated_list)}")

    # 2. Curadoria privada para o SEU WhatsApp (100% Remoto + Português + Sem Inglês Fluente)
    admin_candidates = []
    for kw in ADMIN_PROFILE["keywords"]:
        admin_candidates.extend(fetch_linkedin_guest_jobs(kw, wt_filter="2"))
        time.sleep(1.5)

    new_alerts = 0
    for job in admin_candidates:
        jid = job["job_id"]
        if jid in sent_jobs:
            continue
        details = inspect_job_details(jid, job["title"], job["location"])
        if not details:
            continue
        sent_jobs.add(jid)

        if not details["is_portuguese"] or details["requires_fluent_en"] or details["modality"] != "remoto":
            continue

        match_pct, tags = calculate_admin_match(job["title"], details["full_text_low"])
        if match_pct >= MIN_MATCH_ALERT and new_alerts < 5:
            tags_str = ", ".join(tags) if tags else "Logística / WMS / Dados"
            msg = (
                f"🇧🇷 *NATIVAGAS — {match_pct}% MATCH*\n\n"
                f"🏢 *Empresa:* {job['company']}\n"
                f"💼 *Vaga:* {job['title']}\n"
                f"✅ *Curadoria:* 100% Remoto • Português\n"
                f"🎯 *Skills:* {tags_str}\n\n"
                f"🔗 *Candidatar-se direto:* {job['link']}"
            )
            if send_whatsapp_callmebot(msg):
                new_alerts += 1
                time.sleep(4)
        time.sleep(1.2)

    save_json_file(SENT_CACHE_FILE, list(sent_jobs)[-800:])
    print(f"=== Concluído. Alertas WhatsApp: {new_alerts} ===")

if __name__ == "__main__":
    run_cycle()
