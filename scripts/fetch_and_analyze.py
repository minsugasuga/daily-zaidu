import os
import json
import time
import datetime
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DATA_FILE = "data/articles.json"
TODAY = datetime.date.today().isoformat()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

def classify(title, text):
    t = title + text
    if any(k in t for k in ["民生","就业","医疗","养老","住房","教育","扶贫","乡村","农村","社保","低保"]):
        return "民生新闻"
    if any(k in t for k in ["文化","传统","文艺","文学","非遗","博物馆","节日","习俗","戏曲","诗词"]):
        return "文化"
    if any(k in t for k in ["评论","观点","社论","时评","现象","反思","警惕","深思","值得"]):
        return "社会评论"
    if any(k in t for k in ["党","政策","法规","改革","发展","战略","国家","习近平","全面","推进"]):
        return "国家大事"
    return "社会评论"

def get_page_text(url, encoding="utf-8"):
    """返回原始 response 和 BeautifulSoup"""
    r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
    # 强制编码，不让 requests 自动猜
    r.encoding = encoding
    return r, BeautifulSoup(r.text, "html.parser")

def extract_title(soup, encoding="utf-8"):
    """从详情页提取标题，gbk 页面从 bytes 重新解码"""
    for sel in ["h1.title", "h1", ".title", "#title"]:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(strip=True)
            if 4 < len(t) < 80:
                return t
    t_tag = soup.select_one("title")
    if t_tag:
        raw = t_tag.get_text(strip=True)
        for sep in ["_", "—", "－", "-", "|", "｜"]:
            if sep in raw:
                raw = raw.split(sep)[0].strip()
        if 4 < len(raw) < 80:
            return raw
    return ""

def extract_body(soup):
    for sel in [".rm_txt_con", "#rwb_zw", ".article_box",
                ".article", ".content", ".TRS_Editor", "article"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text
    return ""

def fetch_rmrb():
    articles = []
    sources = [
        ("https://opinion.people.com.cn/", "gbk", "人民日报·评论"),
        ("https://culture.people.com.cn/",  "gbk", "人民日报·文化"),
    ]
    for index_url, enc, source in sources:
        try:
            _, soup = get_page_text(index_url, enc)
            domain = "https://" + index_url.split("/")[2]

            candidates = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".html" not in href:
                    continue
                if href.startswith("http") and "people.com.cn" in href:
                    candidates.append(href)
                elif href.startswith("/n"):
                    candidates.append(domain + href)

            seen = set()
            count = 0
            for link in candidates:
                if count >= 5:
                    break
                if link in seen:
                    continue
                seen.add(link)
                try:
                    _, detail = get_page_text(link, enc)
                    title = extract_title(detail, enc)
                    body  = extract_body(detail)
                    if not title or len(body) < 100:
                        continue
                    articles.append({
                        "title":   title,
                        "source":  source,
                        "url":     link,
                        "content": body[:2000],
                        "date":    TODAY,
                        "cat":     classify(title, body),
                    })
                    count += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"    [skip] {e}")
            print(f"  {source}: {count} pcs")
        except Exception as e:
            print(f"  [WARN] {source}: {e}")
    return articles

def fetch_sxzg():
    articles = []
    url = "http://sxdygbjy.gov.cn/bgz/index.html"
    try:
        _, soup = get_page_text(url, "utf-8")
        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if len(text) < 5 or ".html" not in href:
                continue
            if href.startswith("http"):
                candidates.append(href)
            elif href.startswith("/"):
                candidates.append("http://sxdygbjy.gov.cn" + href)
            elif not href.startswith("#"):
                candidates.append("http://sxdygbjy.gov.cn/bgz/" + href)

        seen = set()
        count = 0
        for link in candidates:
            if count >= 5:
                break
            if link in seen:
                continue
            seen.add(link)
            try:
                _, detail = get_page_text(link, "utf-8")
                title = extract_title(detail)
                body  = extract_body(detail)
                if not title or len(body) < 80:
                    continue
                articles.append({
                    "title":   title,
                    "source":  "山西组工·笔杆子",
                    "url":     link,
                    "content": body[:2000],
                    "date":    TODAY,
                    "cat":     "党政文章",
                })
                count += 1
                time.sleep(1)
            except Exception as e:
                print(f"    [skip] {e}")
        print(f"  sxzg: {count} pcs")
    except Exception as e:
        print(f"  [WARN] sxzg: {e}")
    return articles

def analyze(article):
    if not GEMINI_API_KEY:
        return None
    prompt = f"""你是申论/公文写作备考辅导老师。请分析以下文章，严格只输出JSON，不要任何多余内容，不要markdown代码块。

标题：{article['title']}
来源：{article['source']}
类型：{article['cat']}
正文：
{article['content']}

输出JSON格式：
{{
  "keywords": ["关键词1","关键词2","关键词3","关键词4","关键词5"],
  "excerpt": "核心观点摘要（50字内）",
  "para": "段落结构分析：开篇方式、论证结构、收尾逻辑（150字左右）",
  "skills": ["写作技巧1及文中体现","写作技巧2及文中体现","写作技巧3及文中体现"],
  "why": "从申论/公文写作角度说明摘抄价值，可用于哪类题型场景（100字左右）"
}}"""

    api_url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
    for attempt in range(3):
        try:
            r = requests.post(api_url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
            }, timeout=60, verify=False)
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    rate limit, wait {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e:
            print(f"    [attempt {attempt+1}] {e}")
            time.sleep(10)
    return None

def main():
    os.makedirs("data", exist_ok=True)
    print(f"GEMINI_API_KEY set: {'YES' if GEMINI_API_KEY else 'NO'}")

    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
    existing_urls = {a["url"] for a in existing}

    print("Fetching renminribao...")
    rmrb = fetch_rmrb()
    print("Fetching sxzg...")
    sxzg = fetch_sxzg()

    new_articles = [a for a in rmrb + sxzg if a["url"] not in existing_urls]
    print(f"New: {len(new_articles)}, analyzing...")

    for i, article in enumerate(new_articles):
        print(f"  [{i+1}/{len(new_articles)}] analyzing...")
        result = analyze(article)
        if result:
            article["keywords"] = result.get("keywords", [])
            article["excerpt"]  = result.get("excerpt", "")
            article["analysis"] = {
                "para":   result.get("para", ""),
                "skills": result.get("skills", []),
                "why":    result.get("why", ""),
            }
        else:
            article["keywords"] = []
            article["excerpt"]  = article["content"][:60] + "..."
            article["analysis"] = {"para": "", "skills": [], "why": ""}
        # 每篇分析后等待6秒，避免触发限流
        time.sleep(6)

    all_articles = new_articles + existing
    cutoff = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    all_articles = [a for a in all_articles if a.get("date", "") >= cutoff]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"Done! saved {len(all_articles)} articles.")

if __name__ == "__main__":
    main()
