import os
import re
import json
import time
import base64
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
        '"vaga" ("WMS" OR "Key User") ("remoto" OR "home office" OR "teletrabalho")',
        '"vaga" "Torre de Controle" ("logística" OR "remoto" OR "home office")',
        '"vaga" ("Analista de Logística" OR "Planejamento Logístico") ("remoto" OR "home office" OR "teletrabalho")',
        '"vaga" ("Power BI" OR "SQL" OR "MIS") "logística" ("remoto" OR "home office")',
        '"vaga" ("Comércio Exterior" OR "Comex") ("remoto" OR "home office")',
        'site:gupy.io ("Logística" OR "WMS" OR "Torre de Controle" OR "Power BI") ("Remoto" OR "Home Office")',
        'site:linkedin.com/jobs ("Logística" OR "WMS" OR "Torre de Controle") ("Remoto" OR "Home Office") Brasil'
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
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
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

def resolve_google_news_url(url):
    """Extrai o link final da vaga quando vem encapsulado pelo Google News RSS."""
    if "news.google.com" not in url:
        return url
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if "news.google.com" not in resp.url:
            return resp.url
        # Tenta extrair data-n-au ou URL embutida no HTML de redirecionamento
        m_au = re.search(r'data-n-au="([^"]+)"', resp.text)
        if m_au:
            return m_au.group(1)
        m_http = re.search(r'https?://(?!www\.google|news\.google|fonts\.|gstatic\.)[^\s"\'<>]+', resp.text)
        if m_http:
            return m_http.group(0)
    except Exception:
        pass
    return url

def analyze_full_description(url, title):
    """
    Lê toda a descrição da vaga procurando campos como 'local de trabalho',
    'modelo de trabalho', 'modalidade', 'regime', etc., e verifica se consta
    Remoto, Home Office ou Teletrabalho. Caso negativo, descarta.
    """
    real_url = resolve_google_news_url(url)
    try:
        resp = requests.get(real_url, headers=HEADERS, timeout=15, allow_redirects=True)
        raw_html = resp.text

        # Remove scripts, styles e tags HTML mantendo o texto limpo da descrição
        no_script = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r"<[^>]+>", " ", no_script)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        text_low = clean_text.lower()

        if len(text_low) < 120:
            return False, real_url, "", "Página sem descrição legível"

        # 1. Verifica explicitamente os campos de "local de trabalho" / "modelo" / "modalidade"
        context_patterns = [
            r"(?:local de trabalho|modelo de trabalho|regime de trabalho|modalidade|formato de trabalho|regime|atuação|onde você vai trabalhar)\s*[:\-–]?\s*([^.;\n]{3,90})"
        ]
        extracted_contexts = []
        for pat in context_patterns:
            for m in re.finditer(pat, text_low):
                extracted_contexts.append(m.group(1).strip())

        context_blob = " | ".join(extracted_contexts)

        # Se o campo específico "local/modelo de trabalho" disser presencial ou híbrido, descarta na hora
        if context_blob:
            if any(bad in context_blob for bad in ["presencial", "híbrido", "hibrido", "on-site", "onsite"]):
                return False, real_url, "", f"Campo local/modelo indica presencial/híbrido ({context_blob[:60]})"

        # 2. Verifica termos negativos fortes na descrição completa
        negative_phrases = [
            "100% presencial",
            "trabalho presencial",
            "atuação presencial",
            "atuar presencialmente",
            "vaga presencial",
            "modelo presencial",
            "regime presencial",
            "modelo híbrido",
            "trabalho híbrido",
            "atuação híbrida",
            "vaga híbrida",
            "disponibilidade para atuar presencialmente",
            "não é remoto",
            "não é home office"
        ]
        if any(neg in text_low for neg in negative_phrases):
            return False, real_url, "", "Descrição contém termo presencial/híbrido"

        # 3. Exige confirmação positiva na descrição de Remoto, Home Office ou Teletrabalho
        remote_keywords = [
            "100% remoto",
            "trabalho remoto",
            "modelo remoto",
            "regime remoto",
            "vaga remota",
            "remoto",
            "home office",
            "100% home office",
            "teletrabalho",
            "trabalho à distância",
            "trabalho a distancia"
        ]

        # Prioriza se estiver junto ao contexto de "local/modelo de trabalho", ou claramente na descrição
        found_in_context = any(rk in context_blob for rk in remote_keywords)
        found_in_description = any(rk in text_low for rk in remote_keywords)

        if found_in_context or found_in_description:
            evidence = context_blob[:80] if found_in_context else "Confirmado na descrição da vaga"
            return True, real_url, text_low[:4000], evidence

        return False, real_url, "", "Não consta Remoto, Home Office ou Teletrabalho na descrição"

    except Exception as e:
        return False, real_url, "", f"Não foi possível ler a descrição ({e})"

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
            source_el = item.find("source")
            source_name = source_el.text.strip() if source_el is not None and source_el.text else "Portal Brasil"

            if raw_title and link:
                clean_title = raw_title.rsplit(" - ", 1)[0].strip()
                results.append({
                    "company": source_name,
                    "title": clean_title,
                    "link": link
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
    print(f"=== NATIVAGAS Radar Brasil (Leitura Completa da Descrição): {datetime.now(timezone.utc).isoformat()} ===")
    sent_jobs = load_sent_jobs()
    candidates = []

    for q in CANDIDATE_PROFILE["queries_br"]:
        candidates.extend(fetch_google_news_br_rss(q))
        time.sleep(1)

    print(f"Candidatas brutas coletadas: {len(candidates)}")

    new_alerts = 0
    for job in candidates:
        raw_link = job.get("link", "")
        title = job.get("title", "")
        if not raw_link or not title:
            continue

        job_id = hashlib.md5(title.lower().strip().encode("utf-8")).hexdigest()
        if job_id in sent_jobs:
            continue

        sent_jobs.add(job_id)

        # Lê toda a descrição da vaga (local de trabalho, modelo, etc.)
        is_remote, final_url, full_desc, reason = analyze_full_description(raw_link, title)
        if not is_remote:
            print(f"[Descartada] {title} -> Motivo: {reason}")
            continue

        company = job.get("company", "Portal de Vagas BR")
        match_pct, tags = calculate_match(title, full_desc)

        if match_pct >= MIN_MATCH_ALERT and new_alerts < 5:
            tags_str = ", ".join(tags) if tags else "Logística / WMS / Dados"
            msg = (
                f"🇧🇷 *NATIVAGAS — {match_pct}% MATCH*\n\n"
                f"💼 *Vaga:* {title}\n"
                f"🏢 *Portal/Fonte:* {company}\n"
                f"✅ *Descrição Verificada:* Remoto / Home Office / Teletrabalho\n"
                f"🎯 *Skills na Descrição:* {tags_str}\n\n"
                f"🔗 *Acessar vaga:* {final_url}"
            )
            if send_whatsapp_callmebot(msg):
                new_alerts += 1
                time.sleep(4)

    save_sent_jobs(sent_jobs)
    print(f"=== Varredura concluída. Alertas enviados: {new_alerts} ===")

if __name__ == "__main__":
    run_cycle()
