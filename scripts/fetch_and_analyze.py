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

def get_page(url, encoding="utf-8"):
    """抓取页面，强制指定编码"""
    r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
    r.encoding = encoding
    return BeautifulSoup(r.text, "html.parser")

def extract_title(soup):
    """从页面提取干净标题"""
    # 优先取 h1
    for sel in ["h1.title", "h1", ".title", "#title"]:
        el = soup.select_one(sel)
        if el:
            t = el.get_text(strip=True)
            if 4 < len(t) < 60:
                return t
    # 退而取 <title> 标签，去掉网站名后缀
    t = soup.select_one("title")
    if t:
        raw = t.get_text(strip=True)
        for sep in ["_", "—", "-", "|"]:
            if sep in raw:
                raw = raw.split(sep)[0].strip()
        if 4 < len(raw) < 80:
            return raw
    return ""

def extract_body(soup):
    """提取正文"""
    for sel in [".rm_txt_con", "#rwb_zw", ".article_box", ".article",
                ".content", ".TRS_Editor", "article"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                return text
    return ""

def fetch_rmrb():
    articles = []
    sources = [
        # 评论：用更新的 URL 格式
        ("https://opinion.people.com.cn/", "gbk", "人民日报·评论"),
        ("https://culture.people.com.cn/", "gbk", "人民日报·文化"),
    ]
    for index_url, enc, source in sources:
        try:
            soup = get_page(index_url, enc)
            base = index_url.rstrip("/")

            # 收集所有文章链接
            candidates = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                # 人民网文章 URL 特征：含 /n1/ 或 /n/ 且是 .html
                if len(text) > 5 and (".html" in href):
                    if href.startswith("http") and "people.com.cn" in href:
                        candidates.append((text, href))
                    elif href.startswith("/n"):
                        candidates.append((text, "https://" + index_url.split("/")[2] + href))

            seen = set()
            count = 0
            for _, link in candidates:
                if count >= 6:
                    break
                if link in seen:
                    continue
                seen.add(link)
                try:
                    detail = get_page(link, enc)
                    title = extract_title(detail)
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
                    print(f"    [跳过文章] {e}")
            print(f"  {source}: 获取 {count} 篇")
        except Exception as e:
            print(f"  [WARN] {source} 首页失败: {e}")
    return articles

def fetch_sxzg():
    articles = []
    url = "http://sxdygbjy.gov.cn/bgz/index.html"
    try:
        soup = get_page(url, "utf-8")
        candidates = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if len(text) < 5 or ".html" not in href:
                continue
            if href.startswith("http"):
                candidates.append((text, href))
            elif href.startswith("/"):
                candidates.append((text, "http://sxdygbjy.gov.cn" + href))
            elif not href.startswith("#"):
                candidates.append((text, "http://sxdygbjy.gov.cn/bgz/" + href))

        seen = set()
        count = 0
        for _, link in candidates:
            if count >= 5:
                break
            if link in seen:
                continue
            seen.add(link)
            try:
                detail = get_page(link, "utf-8")
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
                print(f"    [跳过文章] {e}")
        print(f"  山西组工网: 获取 {count} 篇")
    except Exception as e:
        print(f"  [WARN] 山西组工网失败: {e}")
    return articles

def analyze(article):
    if not GEMINI_API_KEY:
        print("  [WARN] GEMINI_API_KEY 未设置")
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

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
    try:
        r = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
        }, timeout=60, verify=False)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"  [WARN] Gemini失败: {e}")
        return None

def main():
    os.makedirs("data", exist_ok=True)
    print(f"GEMINI_API_KEY 已设置: {'是' if GEMINI_API_KEY else '否'}")

    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
    existing_urls = {a["url"] for a in existing}

    print("\n正在抓取人民日报...")
    rmrb = fetch_rmrb()
    print("\n正在抓取山西组工网...")
    sxzg = fetch_sxzg()

    new_articles = [a for a in rmrb + sxzg if a["url"] not in existing_urls]
    print(f"\n新文章 {len(new_articles)} 篇，开始AI分析...")

    for i, article in enumerate(new_articles):
        print(f"  [{i+1}/{len(new_articles)}] {article['title'][:30]}")
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
        time.sleep(2)

    all_articles = new_articles + existing
    cutoff = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    all_articles = [a for a in all_articles if a.get("date", "") >= cutoff]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"\n完成！共保存 {len(all_articles)} 篇文章。")

if __name__ == "__main__":
    main()
