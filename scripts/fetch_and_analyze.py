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
TODAY = datetime.date.today()
DATE_STR  = TODAY.isoformat()            # 2026-06-02
DATE_PATH = TODAY.strftime("%Y%m/%d")    # 202606/02

# 评论=05版，文化=11版
RMRB_NODES = [
    ("https://paper.people.com.cn/rmrb/pc/layout/{date}/node_05.html", "人民日报·评论"),
    ("https://paper.people.com.cn/rmrb/pc/layout/{date}/node_11.html", "人民日报·文化"),
]

SKIP_TITLES = {"图片报道", "纵横", "责编", "版面"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

def classify(title, text):
    t = title + text
    if any(k in t for k in ["民生","就业","医疗","养老","住房","教育","扶贫","乡村","农村","社保","低保"]):
        return "民生新闻"
    if any(k in t for k in ["文化","传统","文艺","文学","非遗","博物馆","节日","习俗","戏曲","诗词"]):
        return "文化"
    if any(k in t for k in ["评论","观点","社论","时评","现象","反思","警惕","深思"]):
        return "社会评论"
    if any(k in t for k in ["党","政策","法规","改革","发展","战略","国家","习近平","全面","推进"]):
        return "国家大事"
    return "社会评论"

def get_soup(url):
    r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
    r.encoding = "utf-8"
    return BeautifulSoup(r.text, "html.parser")

def parse_article(url, source):
    """
    paper.people.com.cn 文章页结构：
    - 标题在 <title> 标签，格式：'文章标题'（无需截断）
    - 正文段落直接在 <body> 里，是 <p> 标签，夹在导航和版权声明之间
    """
    soup = get_soup(url)

    # 1. 取标题：直接用 <title>，去掉末尾可能有的网站名
    title = ""
    t_tag = soup.find("title")
    if t_tag:
        raw = t_tag.get_text(strip=True)
        # 有时格式是 "文章标题_人民网" 或 "文章标题-人民网"
        for sep in [" - 人民网", "_人民网", "－人民网"]:
            if sep in raw:
                raw = raw.split(sep)[0].strip()
        title = raw

    if not title or len(title) < 3:
        return None

    # 过滤噪音条目
    if any(w in title for w in SKIP_TITLES):
        return None

    # 2. 取正文：找页面中所有 <p> 段落，过滤掉导航/版权等噪音
    paragraphs = []
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        # 过滤短段、版权声明、日期行
        if len(text) < 20:
            continue
        if any(w in text for w in ["版权所有", "Copyright", "人民网", "责任编辑", "《人民日报》（"]):
            continue
        paragraphs.append(text)

    body = "\n".join(paragraphs)

    # 如果 <p> 没提取到，fallback：取 # 标题后面的 markdown 正文
    if len(body) < 80:
        full_text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in full_text.split("\n") if len(l.strip()) > 20]
        # 跳过导航部分，找到正文开始
        start = 0
        for i, line in enumerate(lines):
            if title[:8] in line or "第0" in line:
                start = i + 1
                break
        body = "\n".join(lines[start:start+30])

    if len(body) < 80:
        return None

    return {
        "title":   title,
        "source":  source,
        "url":     url,
        "content": body[:2000],
        "date":    DATE_STR,
        "cat":     classify(title, body),
    }

def fetch_rmrb():
    articles = []
    for node_tpl, source in RMRB_NODES:
        url = node_tpl.format(date=DATE_PATH)
        try:
            soup = get_soup(url)
            # 从版面页提取所有 content_ 文章链接
            links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "content_" in href and href.endswith(".html"):
                    full = href if href.startswith("http") else "https://paper.people.com.cn" + href
                    if full not in links:
                        links.append(full)

            print(f"  {source}: found {len(links)} links")
            count = 0
            for link in links:
                if count >= 6:
                    break
                try:
                    article = parse_article(link, source)
                    if article:
                        articles.append(article)
                        count += 1
                        print(f"    + {article['title'][:40]}")
                    time.sleep(1)
                except Exception as e:
                    print(f"    [skip] {e}")
            print(f"  {source}: saved {count} articles")
        except Exception as e:
            print(f"  [WARN] {source}: {e}")
    return articles

def fetch_sxzg():
    articles = []
    url = "http://sxdygbjy.gov.cn/bgz/index.html"
    try:
        soup = get_soup(url)
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if len(text) < 5 or ".html" not in href:
                continue
            if href.startswith("http"):
                links.append(href)
            elif href.startswith("/"):
                links.append("http://sxdygbjy.gov.cn" + href)
            elif not href.startswith("#"):
                links.append("http://sxdygbjy.gov.cn/bgz/" + href)

        seen = set()
        count = 0
        for link in links:
            if count >= 5:
                break
            if link in seen:
                continue
            seen.add(link)
            try:
                detail = get_soup(link)
                # 标题
                title = ""
                t_tag = detail.find("title")
                if t_tag:
                    title = t_tag.get_text(strip=True).split("_")[0].strip()
                if not title:
                    h1 = detail.find("h1")
                    if h1:
                        title = h1.get_text(strip=True)
                # 正文
                body = ""
                for sel in [".article-content", ".TRS_Editor", ".content", "article"]:
                    el = detail.select_one(sel)
                    if el:
                        body = el.get_text(separator="\n", strip=True)
                        if len(body) > 80:
                            break
                if not title or len(body) < 80:
                    continue
                articles.append({
                    "title":   title,
                    "source":  "山西组工·笔杆子",
                    "url":     link,
                    "content": body[:2000],
                    "date":    DATE_STR,
                    "cat":     "党政文章",
                })
                count += 1
                print(f"    + {title[:40]}")
                time.sleep(1)
            except Exception as e:
                print(f"    [skip] {e}")
        print(f"  sxzg: {count} articles")
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
               f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}")
    for attempt in range(4):
        try:
            r = requests.post(api_url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
            }, timeout=60, verify=False)
            if r.status_code == 429:
                wait = 20 * (attempt + 1)
                print(f"    rate limit, wait {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception as e:
            print(f"    [attempt {attempt+1}] {e}")
            time.sleep(5)
    return None

def main():
    os.makedirs("data", exist_ok=True)
    print(f"Date: {DATE_STR}")
    print(f"GEMINI_API_KEY: {'YES' if GEMINI_API_KEY else 'NO'}")

    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
    existing_urls = {a["url"] for a in existing}

    print("--- Fetching people.com.cn (paper edition) ---")
    rmrb = fetch_rmrb()
    print("--- Fetching sxzg ---")
    sxzg = fetch_sxzg()

    new_articles = [a for a in rmrb + sxzg if a["url"] not in existing_urls]
    print(f"--- New: {len(new_articles)}, analyzing... ---")

    for i, article in enumerate(new_articles):
        print(f"  [{i+1}/{len(new_articles)}] analyzing: {article['title'][:30]}")
        result = analyze(article)
        if result:
            article["keywords"] = result.get("keywords", [])
            article["excerpt"]  = result.get("excerpt", "")
            article["analysis"] = {
                "para":   result.get("para", ""),
                "skills": result.get("skills", []),
                "why":    result.get("why", ""),
            }
            print(f"  [{i+1}] OK")
        else:
            article["keywords"] = []
            article["excerpt"]  = article["content"][:60] + "..."
            article["analysis"] = {"para": "", "skills": [], "why": ""}
            print(f"  [{i+1}] analysis skipped")
        time.sleep(5)

    all_articles = new_articles + existing
    cutoff = (TODAY - datetime.timedelta(days=60)).isoformat()
    all_articles = [a for a in all_articles if a.get("date", "") >= cutoff]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"--- Done! {len(all_articles)} articles saved. ---")

if __name__ == "__main__":
    main()
