import os
import re
import json
import time
import hashlib
import urllib.parse
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timezone

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
MIN_MATCH_ALERT = int(os.getenv("MIN_MATCH_ALERT", "65"))
SENT_CACHE_FILE = "sent_jobs.json"
CURATED_WEB_FILE = "vagas_curadas.json"

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

PUBLIC_WEB_QUERIES = [
    {"area": "Bancário & Finanças", "kw": "Bancário", "wt": "2"},
    {"area": "Bancário & Finanças", "kw": "Atendimento Bancário", "wt": ""},
    {"area": "Bancário & Finanças", "kw": "Analista Financeiro", "wt": "2"},
    {"area": "Atendimento & Sucesso", "kw": "Atendimento ao Cliente", "wt": "2"},
    {"area": "Atendimento & Sucesso", "kw": "Customer Success", "wt": "2"},
    {"area": "Operações & Logística", "kw": "Analista Operacional", "wt": "2"},
    {"area": "Operações & Logística", "kw": "Analista de Logística", "wt": "2"},
    {"area": "Recursos Humanos", "kw": "Analista de RH", "wt": "2"},
    {"area": "Tecnologia & Dados", "kw": "Analista de Dados", "wt": "2"},
    {"area": "Comercial & Vendas", "kw": "Consultor Comercial", "wt": "2"}
]

# Plataformas adicionais da lista (FlexJobs, We Work Remotely, Remote.co, Upwork, Indeed, Wellfound, Remotive, NoDesk, Working Nomads, Dynamite Jobs, Arc)
GLOBAL_REMOTE_SITES = [
    {"site_name": "FlexJobs", "domain": "flexjobs.com/publicjobs", "area": "Operações & Logística"},
    {"site_name": "Remote.co", "domain": "remote.co/job", "area": "Atendimento & Sucesso"},
    {"site_name": "Upwork", "domain": "upwork.com/freelance-jobs", "area": "Tecnologia & Dados"},
    {"site_name": "Indeed", "domain": "br.indeed.com/viewjob", "area": "Bancário & Finanças"},
    {"site_name": "Wellfound", "domain": "wellfound.com/jobs", "area": "Tecnologia & Dados"},
    {"site_name": "NoDesk", "domain": "nodesk.co/remote-jobs", "area": "Atendimento & Sucesso"},
    {"site_name": "Dynamite Jobs", "domain": "dynamitejobs.com/company", "area": "Operações & Logística"},
    {"site_name": "Arc", "domain": "arc.dev/remote-jobs", "area": "Tecnologia & Dados"}
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
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

def clean_html(raw_html):
    no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html or "", flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", no_script)
    return re.sub(r"\s+", " ", text).strip()

def classify_area(title, text=""):
    blob = f"{title} {text}".lower()
    if any(k in blob for k in ["financ", "bank", "banc", "account", "credit", "fintech", "contab"]):
        return "Bancário & Finanças"
    if any(k in blob for k in ["support", "customer", "atendimento", "success", "service"]):
        return "Atendimento & Sucesso"
    if any(k in blob for k in ["hr", "human", "recruit", "people", "rh", "talent"]):
        return "Recursos Humanos"
    if any(k in blob for k in ["sales", "account executive", "comercial", "vendas", "marketing", "growth"]):
        return "Comercial & Vendas"
    if any(k in blob for k in ["operat", "logist", "supply", "project", "admin", "manager"]):
        return "Operações & Logística"
    return "Tecnologia & Dados"

# 1. API Oficial Remotive
def fetch_remotive_jobs(limit=15):
    results = []
    try:
        resp = requests.get("https://remotive.com/api/remote-jobs?limit=25", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
        for j in resp.json().get("jobs", [])[:limit]:
            jid = f"remotive_{j.get('id')}"
            title = (j.get("title") or "").strip()
            company = (j.get("company_name") or "Remotive").strip()
            loc = (j.get("candidate_required_location") or "Remoto Global").strip()
            desc = clean_html(j.get("description") or "")
            link = j.get("url") or ""
            if title and link:
                results.append({
                    "job_id": jid,
                    "area": classify_area(title, desc),
                    "title": f"{title} [Remotive]",
                    "company": company,
                    "location": f"Remoto ({loc})",
                    "modality": "remoto",
                    "contract": "pj",
                    "link": link,
                    "excerpt": desc[:420] + ("..." if len(desc) > 420 else ""),
                    "full_text": desc[:4000].lower(),
                    "curated_at": datetime.now(timezone.utc).isoformat()
                })
    except Exception as e:
        print(f"[Aviso Remotive] {e}")
    return results

# 2. API Oficial Working Nomads
def fetch_working_nomads_jobs(limit=15):
    results = []
    try:
        resp = requests.get("https://www.workingnomads.com/api/exposed_jobs/", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
        for j in resp.json()[:limit]:
            title = (j.get("title") or "").strip()
            company = (j.get("company_name") or "Working Nomads").strip()
            loc = (j.get("location") or "Remoto Global").strip()
            desc = clean_html(j.get("description") or "")
            link = j.get("url") or ""
            jid = "wn_" + hashlib.md5(link.encode("utf-8")).hexdigest()[:12]
            if title and link:
                results.append({
                    "job_id": jid,
                    "area": classify_area(title, desc),
                    "title": f"{title} [Working Nomads]",
                    "company": company,
                    "location": f"Remoto ({loc})",
                    "modality": "remoto",
                    "contract": "pj",
                    "link": link,
                    "excerpt": desc[:420] + ("..." if len(desc) > 420 else ""),
                    "full_text": desc[:4000].lower(),
                    "curated_at": datetime.now(timezone.utc).isoformat()
                })
    except Exception as e:
        print(f"[Aviso Working Nomads] {e}")
    return results

# 3. Feed Oficial We Work Remotely (RSS)
def fetch_weworkremotely_jobs(limit=15):
    results = []
    try:
        resp = requests.get("https://weworkremotely.com/remote-jobs.rss", headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item")[:limit]:
            raw_title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = clean_html(item.findtext("description") or "")
            region = (item.findtext("region") or "Remoto Global").strip()
            parts = raw_title.split(":", 1)
            company = parts[0].strip() if len(parts) > 1 else "We Work Remotely"
            title = parts[1].strip() if len(parts) > 1 else raw_title
            jid = "wwr_" + hashlib.md5(link.encode("utf-8")).hexdigest()[:12]
            if title and link:
                results.append({
                    "job_id": jid,
                    "area": classify_area(title, desc),
                    "title": f"{title} [We Work Remotely]",
                    "company": company,
                    "location": f"Remoto ({region})",
                    "modality": "remoto",
                    "contract": "pj",
                    "link": link,
                    "excerpt": desc[:420] + ("..." if len(desc) > 420 else ""),
                    "full_text": desc[:4000].lower(),
                    "curated_at": datetime.now(timezone.utc).isoformat()
                })
    except Exception as e:
        print(f"[Aviso We Work Remotely] {e}")
    return results

# 4. Varredura nos demais portais da lista (FlexJobs, Remote.co, Upwork, Indeed, Wellfound, NoDesk, Dynamite Jobs, Arc)
def fetch_indexed_portal_jobs():
    results = []
    for site in GLOBAL_REMOTE_SITES:
        query = f'site:{site["domain"]} ("remote" OR "remoto")'
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            blocks = re.findall(
                r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?result__snippet[^>]*>(.*?)</a>',
                resp.text,
                flags=re.DOTALL
            )
            for raw_href, raw_title, raw_snippet in blocks[:4]:
                # Extrai URL limpa do redirecionador DuckDuckGo
                m_uddg = re.search(r'uddg=([^&]+)', raw_href)
                clean_link = urllib.parse.unquote(m_uddg.group(1)) if m_uddg else raw_href
                title = clean_html(raw_title)
                snippet = clean_html(raw_snippet)
                if not title or not clean_link.startswith("http"):
                    continue
                jid = f"{site['site_name'].lower().replace(' ', '')}_" + hashlib.md5(clean_link.encode("utf-8")).hexdigest()[:12]
                results.append({
                    "job_id": jid,
                    "area": classify_area(title, snippet) or site["area"],
                    "title": f"{title} [{site['site_name']}]",
                    "company": f"Via {site['site_name']}",
                    "location": "100% Remoto",
                    "modality": "remoto",
                    "contract": "pj" if site["site_name"] in ["Upwork", "Arc"] else "clt",
                    "link": clean_link,
                    "excerpt": snippet[:420] if snippet else f"Vaga remota verificada no portal {site['site_name']}.",
                    "full_text": f"{title} {snippet}".lower(),
                    "curated_at": datetime.now(timezone.utc).isoformat()
                })
        except Exception as e:
            print(f"[Aviso {site['site_name']}] {e}")
        time.sleep(1.5)
    return results

# 5. LinkedIn Brasil
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
            title = clean_html(raw_title)
            company = clean_html(raw_company)
            location = clean_html(raw_loc)
            if job_id and title:
                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company or "Empresa no LinkedIn",
                    "location": location or "Brasil",
                    "link": f"https://www.linkedin.com/jobs/view/{job_id}/"
                })
    except Exception as e:
        print(f"[Erro LinkedIn '{keyword}'] {e}")
    return jobs

def inspect_linkedin_details(job_id, title, location_str):
    detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        desc_match = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', resp.text, flags=re.DOTALL)
        raw_desc = desc_match.group(1) if desc_match else resp.text
        clean_text = clean_html(raw_desc)
        text_low = clean_text.lower()
        full_check = f"{title.lower()} {location_str.lower()} {text_low}"

        modality = "presencial"
        if any(k in full_check for k in ["100% remoto", "trabalho remoto", "modelo remoto", "home office", "teletrabalho", "remoto"]):
            modality = "remoto"
        elif any(k in full_check for k in ["híbrido", "hibrido", "modelo híbrido", "trabalho híbrido"]):
            modality = "hibrido"

        contract = "clt"
        if any(k in full_check for k in ["pessoa jurídica", "contratação pj", "regime pj", " pj "]):
            contract = "pj"
        elif "estágio" in full_check or "estagio" in full_check:
            contract = "intern"

        pt_markers = ["requisitos", "atividades", "responsabilidades", "experiência", "benefícios", "sobre a vaga", "descrição"]
        is_portuguese = sum(1 for m in pt_markers if m in text_low) >= 2
        requires_fluent_en = any(eng in full_check for eng in [
            "inglês fluente", "ingles fluente", "inglês avançado", "ingles avancado",
            "fluent english", "advanced english", "bilíngue", "bilingue"
        ])

        return {
            "description_excerpt": clean_text[:420] + ("..." if len(clean_text) > 420 else ""),
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
    print(f"=== NATIVAGAS Curadoria Multi-Plataformas (12 Portais): {datetime.now(timezone.utc).isoformat()} ===")
    sent_jobs = set(load_json_file(SENT_CACHE_FILE, []))
    existing_web_jobs = load_json_file(CURATED_WEB_FILE, {"jobs": []}).get("jobs", [])
    web_jobs_map = {j["job_id"]: j for j in existing_web_jobs if "job_id" in j}

    # Coleta das plataformas remotas (Remotive, Working Nomads, We Work Remotely, FlexJobs, Remote.co, Upwork, Indeed, Wellfound, NoDesk, Dynamite Jobs, Arc)
    external_jobs = []
    external_jobs.extend(fetch_remotive_jobs(limit=15))
    external_jobs.extend(fetch_working_nomads_jobs(limit=15))
    external_jobs.extend(fetch_weworkremotely_jobs(limit=15))
    external_jobs.extend(fetch_indexed_portal_jobs())

    for ej in external_jobs:
        web_jobs_map[ej["job_id"]] = ej

    # Coleta LinkedIn Brasil
    for item in PUBLIC_WEB_QUERIES:
        raw_list = fetch_linkedin_guest_jobs(item["kw"], wt_filter=item["wt"])[:8]
        for job in raw_list:
            jid = job["job_id"]
            if jid in web_jobs_map:
                continue
            details = inspect_linkedin_details(jid, job["title"], job["location"])
            if not details or not details["is_portuguese"]:
                continue
            web_jobs_map[jid] = {
                "job_id": jid,
                "area": item["area"],
                "title": f"{job['title']} [LinkedIn]",
                "company": job["company"],
                "location": job["location"],
                "modality": details["modality"],
                "contract": details["contract"],
                "link": job["link"],
                "excerpt": details["description_excerpt"],
                "full_text": details["full_text_low"],
                "curated_at": datetime.now(timezone.utc).isoformat()
            }
            time.sleep(1.2)
        time.sleep(1.2)

    curated_list = list(web_jobs_map.values())[-260:]
    curated_list.reverse()
    save_json_file(CURATED_WEB_FILE, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(curated_list),
        "jobs": curated_list
    })
    print(f"Total de vagas reais consolidadas dos 12 portais: {len(curated_list)}")

    # Alertas privados no WhatsApp
    admin_candidates = []
    for kw in ADMIN_PROFILE["keywords"]:
        admin_candidates.extend(fetch_linkedin_guest_jobs(kw, wt_filter="2"))
        time.sleep(1.5)

    new_alerts = 0
    for job in admin_candidates:
        jid = job["job_id"]
        if jid in sent_jobs:
            continue
        details = inspect_linkedin_details(jid, job["title"], job["location"])
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
