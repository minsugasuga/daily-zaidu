# 每日摘读 📋

每天自动从人民日报、山西组工网抓取文章，用 Claude AI 分析关键词、段落结构与写作技巧，供申论/公文写作备考使用。

---

## 快速部署（5步）

### 第1步：Fork 本仓库
点击右上角 **Fork** 按钮，复制到你自己的 GitHub 账号下。

### 第2步：获取 Claude API Key
前往 [https://console.anthropic.com](https://console.anthropic.com) 注册并获取 API Key（形如 `sk-ant-...`）。

### 第3步：添加 Secret
在你的仓库页面：
```
Settings → Secrets and variables → Actions → New repository secret
```
- Name: `ANTHROPIC_API_KEY`
- Value: 你的 API Key

### 第4步：开启 GitHub Pages
在你的仓库页面：
```
Settings → Pages → Source 选择 "Deploy from a branch" → Branch 选 main → / (root) → Save
```
稍等1-2分钟，你的网页地址就是：
```
https://你的用户名.github.io/daily-zaidu/
```

### 第5步：手动触发第一次抓取
```
Actions → 每日文章抓取与分析 → Run workflow → Run workflow
```
等待约3-5分钟完成后，刷新网页即可看到今日文章。

---

## 之后完全自动
每天北京时间早上 **9:00** 自动运行，无需任何操作。

---

## 文件结构
```
├── index.html                  # 前端网页
├── data/
│   └── articles.json           # 文章数据（自动更新）
├── scripts/
│   └── fetch_and_analyze.py    # 抓取+AI分析脚本
└── .github/workflows/
    └── daily.yml               # GitHub Actions 定时任务
```

---

## 数据来源
- [人民日报·评论](https://opinion.people.com.cn/)
- [人民日报·文化](https://culture.people.com.cn/)
- [山西组工网·笔杆子](http://sxdygbjy.gov.cn/bgz/index.html)
