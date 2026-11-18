import os
import re
import json
import time
import urllib.parse
import requests
from datetime import datetime, timezone

WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER", "5511959074897")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")
MIN_MATCH_ALERT = int(os.getenv("MIN_MATCH_ALERT", "65"))
SENT_CACHE_FILE = "sent_jobs.json"

CANDIDATE_PROFILE = {
    "name": "Natália Cristine",
    "linkedin_keywords_br": [
        "WMS",
        "Key User WMS",
        "Torre de Controle",
        "Analista de Logística",
        "Planejamento Logístico",
        "Power BI Logística",
        "MIS",
        "Comércio Exterior"
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9"
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

def fetch_linkedin_guest_jobs(keyword):
    encoded_kw = urllib.parse.quote(keyword)
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={encoded_kw}&location=Brazil&f_WT=2&f_TPR=r86400&start=0"
    jobs = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[Aviso LinkedIn Search '{keyword}'] HTTP {resp.status_code}")
            return jobs

        cards = re.findall(
            r'data-entity-urn="urn:li:jobPosting:(\d+)".*?base-search-card__title[^>]*>(.*?)</h3>.*?base-search-card__subtitle[^>]*>(.*?)</h4>',
            resp.text,
            flags=re.DOTALL
        )
        for job_id, raw_title, raw_company in cards:
            title = re.sub(r"<[^>]+>", "", raw_title).strip()
            company = re.sub(r"<[^>]+>", "", raw_company).strip()
            if job_id and title:
                jobs.append({
                    "job_id": job_id,
                    "title": title,
                    "company": company or "Empresa no LinkedIn",
                    "link": f"https://www.linkedin.com/jobs/view/{job_id}/"
                })
    except Exception as e:
        print(f"[Erro LinkedIn Search '{keyword}'] {e}")
    return jobs

def inspect_linkedin_job_description(job_id, title):
    """
    Lê a descrição completa da vaga e só aprova se:
    1. Estiver em português;
    2. NÃO exigir inglês avançado/fluente;
    3. NÃO mencionar presencial/híbrido;
    4. Confirmar EXPLICITAMENTE Remoto, Home Office ou Teletrabalho no texto.
    """
    detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return False, "", f"Não foi possível ler a descrição (HTTP {resp.status_code})"

        no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", resp.text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r"<[^>]+>", " ", no_script)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        text_low = clean_text.lower()
        full_check = f"{title.lower()} {text_low}"

        # 1. Garante que a vaga está escrita em português
        pt_markers = ["requisitos", "atividades", "responsabilidades", "experiência", "benefícios", "contratação", "sobre a vaga", "local de trabalho"]
        if sum(1 for m in pt_markers if m in text_low) < 2:
            return False, "", "Vaga em inglês ou sem descrição detalhada em português"

        # 2. Bloqueia exigência de inglês fluente / avançado / bilíngue
        english_requirements = [
            "inglês fluente", "ingles fluente",
            "inglês avançado", "ingles avancado",
            "inglês imprescindível", "ingles imprescindivel",
            "inglês obrigatório", "ingles obrigatorio",
            "fluent english", "advanced english",
            "english fluency", "bilíngue", "bilingue",
            "conversação em inglês", "conversacao em ingles"
        ]
        if any(eng in full_check for eng in english_requirements):
            return False, "", "Exige inglês fluente/avançado"

        # 3. Verifica campos específicos de local/modelo de trabalho
        context_patterns = [
            r"(?:local de trabalho|modelo de trabalho|regime de trabalho|modalidade|formato de trabalho|regime|atuação)\s*[:\-–]?\s*([^.;\n]{3,90})"
        ]
        extracted_contexts = []
        for pat in context_patterns:
            for m in re.finditer(pat, text_low):
                extracted_contexts.append(m.group(1).strip())

        context_blob = " | ".join(extracted_contexts)
        if context_blob and any(bad in context_blob for bad in ["presencial", "híbrido", "hibrido", "on-site"]):
            return False, "", f"Local/modelo indica presencial/híbrido ({context_blob[:50]})"

        # 4. Bloqueia qualquer menção a presencial ou híbrido na descrição
        negative_phrases = [
            "100% presencial", "trabalho presencial", "atuação presencial",
            "atuar presencialmente", "vaga presencial", "modelo presencial",
            "regime presencial", "modelo híbrido", "trabalho híbrido",
            "atuação híbrida", "vaga híbrida", "regime híbrido"
        ]
        if any(neg in full_check for neg in negative_phrases):
            return False, "", "Descrição menciona trabalho presencial ou híbrido"

        # 5. Exige confirmação explícita de Remoto, Home Office ou Teletrabalho
        remote_keywords = [
            "100% remoto", "trabalho remoto", "modelo remoto", "regime remoto",
            "vaga remota", "remoto", "home office", "100% home office",
            "teletrabalho", "trabalho à distância", "trabalho a distancia"
        ]
        if any(rk in full_check for rk in remote_keywords):
            return True, text_low[:4000], "Confirmado: 100% Remoto e sem inglês fluente"

        return False, "", "Não consta Remoto, Home Office ou Teletrabalho na descrição"
    except Exception as e:
        return False, "", f"Erro ao validar descrição ({e})"

def calculate_match(title, description):
    text = f"{title} {description}".lower()
    score = 48
    matched_tags = []
    for skill, weight in CANDIDATE_PROFILE["core_skills"].items():
        if skill in text:
            score += weight
            tag = skill.upper()
            if tag not in matched_tags:
                matched_tags.append(tag)
    return min(score, 99), matched_tags[:6]

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
    print(f"=== NATIVAGAS LinkedIn Brasil (Estrito Remoto + Sem Inglês Fluente): {datetime.now(timezone.utc).isoformat()} ===")
    sent_jobs = load_sent_jobs()
    candidates = []

    for kw in CANDIDATE_PROFILE["linkedin_keywords_br"]:
        candidates.extend(fetch_linkedin_guest_jobs(kw))
        time.sleep(2)

    print(f"Candidatas coletadas no LinkedIn Brasil: {len(candidates)}")

    new_alerts = 0
    for job in candidates:
        job_id = job["job_id"]
        if job_id in sent_jobs:
            continue

        title = job["title"]
        company = job["company"]
        link = job["link"]

        is_valid, full_desc, reason = inspect_linkedin_job_description(job_id, title)
        
        # Só salva no cache definitivo se foi lida com sucesso; se deu rate-limit HTTP 429, tenta novamente na próxima rodada
        if "HTTP 429" not in reason:
            sent_jobs.add(job_id)

        if not is_valid:
            print(f"[Descartada] {title} ({company}) -> {reason}")
            time.sleep(1.5)
            continue

        match_pct, tags = calculate_match(title, full_desc)
        if match_pct >= MIN_MATCH_ALERT and new_alerts < 5:
            tags_str = ", ".join(tags) if tags else "Logística / WMS / Dados"
            msg = (
                f"🇧🇷 *NATIVAGAS — {match_pct}% MATCH*\n\n"
                f"🏢 *Empresa:* {company}\n"
                f"💼 *Vaga:* {title}\n"
                f"✅ *Validado:* 100% Remoto • Português\n"
                f"🎯 *Skills:* {tags_str}\n\n"
                f"🔗 *Candidatar-se direto:* {link}"
            )
            if send_whatsapp_callmebot(msg):
                new_alerts += 1
                time.sleep(4)

        time.sleep(1.5)

    save_sent_jobs(sent_jobs)
    print(f"=== Varredura concluída. Alertas enviados: {new_alerts} ===")

if __name__ == "__main__":
    run_cycle()
