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

def safe_get(url, encoding="utf-8"):
    r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
    # 强制指定编码，不依赖自动检测
    r.encoding = encoding
    return r

def decode_title(raw):
    """修复乱码标题：尝试 latin1 -> gbk 转换"""
    try:
        return raw.encode("latin1").decode("gbk")
    except Exception:
        return raw

def fetch_rmrb():
    articles = []
    sources = [
        ("https://opinion.people.com.cn/GB/8213/index.html", "gbk", "人民日报·评论"),
        ("https://culture.people.com.cn/GB/22219/index.html", "gbk", "人民日报·文化"),
    ]
    for url, enc, source in sources:
        try:
            r = safe_get(url, enc)
            soup = BeautifulSoup(r.text, "html.parser")
            base = "/".join(url.split("/")[:3])
            links = []
            for a in soup.select("a[href]"):
                href = a["href"]
                text = a.get_text(strip=True)
                if len(text) < 8:
                    continue
                if href.startswith("http"):
                    links.append((text, href))
                elif href.startswith("/"):
                    links.append((text, base + href))

            seen = set()
            count = 0
            for title, link in links:
                if count >= 6:
                    break
                if link in seen:
                    continue
                seen.add(link)
                try:
                    pr = requests.get(link, headers=HEADERS, timeout=15, verify=False)
                    # 人民网 GB 系列页面固定 gbk
                    pr.encoding = "gbk"
                    ps = BeautifulSoup(pr.text, "html.parser")

                    # 从页面 <title> 或 h1 重新取标题（避免列表页乱码）
                    page_title = ""
                    h1 = ps.select_one("h1")
                    if h1:
                        page_title = h1.get_text(strip=True)
                    if not page_title:
                        t_tag = ps.select_one("title")
                        if t_tag:
                            page_title = t_tag.get_text(strip=True).split("_")[0].strip()
                    final_title = page_title if page_title else title

                    body = (ps.select_one(".rm_txt_con") or
                            ps.select_one("#rwb_zw") or
                            ps.select_one(".article"))
                    content = body.get_text(separator="\n", strip=True) if body else ""
                    if len(content) < 100:
                        continue

                    articles.append({
                        "title": final_title,
                        "source": source,
                        "url": link,
                        "content": content[:2000],
                        "date": TODAY,
                        "cat": classify(final_title, content),
                    })
                    count += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"  [跳过] {e}")
                    continue
            print(f"  {source}: 获取 {count} 篇")
        except Exception as e:
            print(f"[WARN] {source} 首页失败: {e}")
    return articles

def fetch_sxzg():
    articles = []
    url = "http://sxdygbjy.gov.cn/bgz/index.html"
    try:
        r = safe_get(url, "utf-8")
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.select("a[href]"):
            href = a["href"]
            text = a.get_text(strip=True)
            if len(text) < 6 or ".html" not in href:
                continue
            if href.startswith("http"):
                links.append((text, href))
            elif href.startswith("/"):
                links.append((text, "http://sxdygbjy.gov.cn" + href))
            else:
                links.append((text, "http://sxdygbjy.gov.cn/bgz/" + href))

        seen = set()
        count = 0
        for title, link in links:
            if count >= 5:
                break
            if link in seen:
                continue
            seen.add(link)
            try:
                pr = safe_get(link, "utf-8")
                ps = BeautifulSoup(pr.text, "html.parser")

                page_title = ""
                h1 = ps.select_one("h1")
                if h1:
                    page_title = h1.get_text(strip=True)
                if not page_title:
                    t_tag = ps.select_one("title")
                    if t_tag:
                        page_title = t_tag.get_text(strip=True).split("_")[0].strip()
                final_title = page_title if page_title else title

                body = (ps.select_one(".article-content") or
                        ps.select_one(".TRS_Editor") or
                        ps.select_one(".content") or
                        ps.select_one("article"))
                content = body.get_text(separator="\n", strip=True) if body else ""
                if len(content) < 80:
                    continue

                articles.append({
                    "title": final_title,
                    "source": "山西组工·笔杆子",
                    "url": link,
                    "content": content[:2000],
                    "date": TODAY,
                    "cat": "党政文章",
                })
                count += 1
                time.sleep(1)
            except Exception as e:
                print(f"  [跳过] {e}")
                continue
        print(f"  山西组工网: 获取 {count} 篇")
    except Exception as e:
        print(f"[WARN] 山西组工网失败: {e}")
    return articles

def analyze(article):
    if not GEMINI_API_KEY:
        print("  [WARN] GEMINI_API_KEY 未设置，跳过AI分析")
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

    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
    }
    try:
        r = requests.post(api_url, json=payload, timeout=60, verify=False)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        clean = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"  [WARN] Gemini失败: {e}")
        return None

def main():
    os.makedirs("data", exist_ok=True)
    print(f"GEMINI_API_KEY 已设置: {'是' if GEMINI_API_KEY else '否（将跳过AI分析）'}")

    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing_urls = {a["url"] for a in existing}

    print("\n正在抓取人民日报...")
    rmrb = fetch_rmrb()
    print("\n正在抓取山西组工网...")
    sxzg = fetch_sxzg()

    new_articles = [a for a in rmrb + sxzg if a["url"] not in existing_urls]
    print(f"\n新文章 {len(new_articles)} 篇，开始AI分析...")

    for i, article in enumerate(new_articles):
        print(f"  [{i+1}/{len(new_articles)}] {article['title'][:25]}")
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
