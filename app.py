from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import sys
import traceback
import uuid
import warnings
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

warnings.filterwarnings("ignore", message="'cgi' is deprecated.*", category=DeprecationWarning)
import cgi

import fitz

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
PAGE_DIR = DATA_DIR / "pages"
STATIC_DIR = ROOT / "static"
DB_PATH = DATA_DIR / "gaoshu_demo.sqlite3"

PORT = int(os.getenv("PORT", "8000"))
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEFAULT_SUBJECT = "未分类"
DEFAULT_CATEGORY = "待归类"
DEFAULT_CHAPTER = "未识别章节"
REVIEW_INTERVAL_DAYS = [1, 3, 7, 14, 30]
META_TAGS = ["计算失误", "公式遗忘", "逻辑死角", "题意理解偏差"]
WRONGISH_STATUSES = {"做错", "半会", "需复习"}
KNOWLEDGE_DEPENDENCIES = {
    "微分方程": ["不定积分", "导数与微分"],
    "重积分": ["定积分及其应用", "不定积分"],
    "多元函数微分学": ["导数与微分", "函数、极限与连续"],
    "无穷级数": ["函数、极限与连续", "导数与微分"],
    "导数应用": ["导数与微分", "函数、极限与连续"],
    "定积分及其应用": ["不定积分", "函数、极限与连续"],
    "概率统计": ["函数、极限与连续"],
}

KEYWORD_RULES = [
    ("无穷级数", ["级数", "收敛", "发散", "收敛半径", "幂级数", "泰勒", "麦克劳林", "傅里叶", "sum", "∑"]),
    ("函数、极限与连续", ["极限", "连续", "无穷小", "等价", "洛必达", "lim", "趋于"]),
    ("导数与微分", ["导数", "微分", "求导", "偏导", "可导"]),
    ("微分中值定理", ["中值定理", "罗尔", "拉格朗日", "柯西"]),
    ("导数应用", ["单调", "极值", "最值", "凹凸", "拐点", "渐近线"]),
    ("不定积分", ["不定积分", "原函数", "换元积分", "分部积分"]),
    ("定积分及其应用", ["定积分", "面积", "体积", "弧长", "反常积分"]),
    ("多元函数微分学", ["多元", "全微分", "方向导数", "梯度", "条件极值"]),
    ("重积分", ["二重积分", "三重积分", "极坐标", "柱坐标", "球坐标"]),
    ("微分方程", ["微分方程", "通解", "特解", "初值", "齐次方程"]),
    ("向量代数与空间解析几何", ["向量", "平面", "直线", "曲面", "空间", "法向量"]),
    ("线性代数", ["矩阵", "行列式", "特征值", "特征向量", "线性相关", "线性无关", "秩", "向量组"]),
    ("概率统计", ["概率", "随机变量", "分布函数", "密度函数", "期望", "方差", "假设检验", "置信区间"]),
    ("英语阅读", ["reading", "passage", "paragraph", "comprehension", "main idea"]),
    ("英语写作", ["essay", "writing", "translation", "作文", "翻译"]),
    ("政治理论", ["马克思", "毛泽东", "新时代", "中国特色社会主义", "哲学", "史纲"]),
]


def ensure_dirs() -> None:
    for path in (DATA_DIR, UPLOAD_DIR, PAGE_DIR, STATIC_DIR):
        path.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '未分类',
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                page_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                ocr_text TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '',
                chapter TEXT NOT NULL DEFAULT '未识别章节',
                difficulty TEXT NOT NULL DEFAULT '中等',
                status TEXT NOT NULL DEFAULT '未做',
                mistake_reason TEXT NOT NULL DEFAULT '',
                user_note TEXT NOT NULL DEFAULT '',
                ai_analysis TEXT NOT NULL DEFAULT '',
                ai_variations TEXT NOT NULL DEFAULT '',
                ai_hint TEXT NOT NULL DEFAULT '',
                meta_tags TEXT NOT NULL DEFAULT '[]',
                review_count INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at TEXT,
                ever_wrong INTEGER NOT NULL DEFAULT 0,
                review_stage INTEGER NOT NULL DEFAULT 0,
                retention_stage INTEGER NOT NULL DEFAULT 0,
                next_review_at TEXT,
                mastered_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            """
        )
        migrate_db(conn)
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
            CREATE INDEX IF NOT EXISTS idx_questions_chapter ON questions(chapter);
            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            CREATE INDEX IF NOT EXISTS idx_questions_document ON questions(document_id);
            CREATE INDEX IF NOT EXISTS idx_questions_next_review ON questions(next_review_at);
            """
        )


def migrate_db(conn: sqlite3.Connection) -> None:
    document_columns = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "title" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN title TEXT NOT NULL DEFAULT ''")
    if "subject" not in document_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN subject TEXT NOT NULL DEFAULT '未分类'")
    conn.execute("UPDATE documents SET title = filename WHERE title = ''")
    conn.execute("UPDATE documents SET subject = ? WHERE subject = '' OR subject = '其他'", (DEFAULT_SUBJECT,))

    question_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)").fetchall()}
    if "chapter" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN chapter TEXT NOT NULL DEFAULT '未识别章节'")
    if "ai_variations" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN ai_variations TEXT NOT NULL DEFAULT ''")
    if "ai_hint" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN ai_hint TEXT NOT NULL DEFAULT ''")
    if "meta_tags" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN meta_tags TEXT NOT NULL DEFAULT '[]'")
    if "ever_wrong" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN ever_wrong INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE questions SET ever_wrong = 1 WHERE status IN ('做错', '半会', '需复习')")
    if "review_stage" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN review_stage INTEGER NOT NULL DEFAULT 0")
    if "retention_stage" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN retention_stage INTEGER NOT NULL DEFAULT 0")
    if "next_review_at" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN next_review_at TEXT")
    if "mastered_at" not in question_columns:
        conn.execute("ALTER TABLE questions ADD COLUMN mastered_at TEXT")
    conn.execute("UPDATE questions SET chapter = ? WHERE chapter = ''", (DEFAULT_CHAPTER,))
    conn.execute("UPDATE questions SET meta_tags = '[]' WHERE meta_tags = ''")


def to_public_path(path: str | Path) -> str:
    absolute = Path(path).resolve()
    return "/" + absolute.relative_to(ROOT).as_posix()


def row_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["image_url"] = to_public_path(item["image_path"])
    try:
        item["meta_tags"] = json.loads(item.get("meta_tags") or "[]")
    except (TypeError, json.JSONDecodeError):
        item["meta_tags"] = []
    return item


def document_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def schedule_for_status(current: sqlite3.Row | dict | None, status: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    if status in WRONGISH_STATUSES:
        return {
            "ever_wrong": 1,
            "review_stage": 0,
            "retention_stage": 1,
            "next_review_at": (now + timedelta(days=1)).date().isoformat(),
            "mastered_at": None,
        }
    if status != "做对" or not current:
        return {}

    current_dict = dict(current)
    was_in_review = bool(current_dict.get("ever_wrong")) or current_dict.get("status") in {"做错", "半会", "需复习"}
    if not was_in_review:
        return {}

    next_stage = int(current_dict.get("review_stage") or 0) + 1
    if next_stage > len(REVIEW_INTERVAL_DAYS):
        return {
            "ever_wrong": 1,
            "review_stage": next_stage,
            "retention_stage": REVIEW_INTERVAL_DAYS[-1],
            "next_review_at": None,
            "mastered_at": now.isoformat(timespec="seconds"),
        }
    interval = REVIEW_INTERVAL_DAYS[next_stage - 1]
    return {
        "ever_wrong": 1,
        "review_stage": next_stage,
        "retention_stage": interval,
        "next_review_at": (now + timedelta(days=interval)).date().isoformat(),
        "mastered_at": None,
    }


def get_filter_options(conn: sqlite3.Connection) -> dict:
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE subject <> '' ORDER BY subject"
        ).fetchall()
    ]
    categories = [
        row["category"]
        for row in conn.execute(
            """
            SELECT category, MIN(page_number) first_page
            FROM questions
            WHERE category <> ''
            GROUP BY category
            ORDER BY first_page ASC, category ASC
            """
        ).fetchall()
    ]
    chapters = [
        row["chapter"]
        for row in conn.execute(
            """
            SELECT chapter, MIN(page_number) first_page
            FROM questions
            WHERE chapter <> ''
            GROUP BY chapter
            ORDER BY first_page ASC, chapter ASC
            """
        ).fetchall()
    ]
    return {"subjects": subjects, "categories": categories, "chapters": chapters}


def build_question_filters(query: dict, keys: tuple[str, ...]) -> tuple[str, list[str]]:
    clauses = []
    params: list[str] = []
    for key in ("category", "status", "document_id", "chapter"):
        value = query.get(key, [""])[0]
        if value and key in keys:
            clauses.append(f"q.{key} = ?")
            params.append(value)
    subject = query.get("subject", [""])[0]
    if subject and "subject" in keys:
        clauses.append("d.subject = ?")
        params.append(subject)
    search = query.get("search", [""])[0].strip()
    if search and "search" in keys:
        clauses.append("(q.ocr_text LIKE ? OR q.subcategory LIKE ? OR q.user_note LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def get_scoped_filter_options(conn: sqlite3.Connection, query: dict) -> dict:
    subjects = [
        row["subject"]
        for row in conn.execute(
            "SELECT DISTINCT subject FROM documents WHERE subject <> '' ORDER BY subject"
        ).fetchall()
    ]
    category_where, category_params = build_question_filters(
        query,
        ("status", "document_id", "chapter", "subject", "search"),
    )
    category_where = f"{category_where} AND q.category <> ''" if category_where else "WHERE q.category <> ''"
    categories = [
        row["category"]
        for row in conn.execute(
            f"""
            SELECT q.category, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {category_where}
            GROUP BY q.category
            ORDER BY first_page ASC, q.category ASC
            """,
            category_params,
        ).fetchall()
    ]
    chapter_where, chapter_params = build_question_filters(
        query,
        ("category", "status", "document_id", "subject", "search"),
    )
    chapter_where = f"{chapter_where} AND q.chapter <> ''" if chapter_where else "WHERE q.chapter <> ''"
    chapters = [
        row["chapter"]
        for row in conn.execute(
            f"""
            SELECT q.chapter, MIN(q.page_number) first_page
            FROM questions q
            JOIN documents d ON d.id = q.document_id
            {chapter_where}
            GROUP BY q.chapter
            ORDER BY first_page ASC, q.chapter ASC
            """,
            chapter_params,
        ).fetchall()
    ]
    return {"subjects": subjects, "categories": categories, "chapters": chapters}


def json_response(handler: BaseHTTPRequestHandler, payload: dict | list, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200, content_type: str = "text/plain") -> None:
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def classify_by_rules(text: str) -> tuple[str, str, str]:
    haystack = text.lower()
    for category, keywords in KEYWORD_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category, "规则分类", "中等"
    return DEFAULT_CATEGORY, "待人工确认", "中等"


def normalize_label(value: str, fallback: str) -> str:
    clean = re.sub(r"\s+", " ", (value or "").strip())
    clean = re.sub(r"^[\-\s|·•]+|[\-\s|·•]+$", "", clean)
    return clean[:80] if clean else fallback


def normalize_chapter(value: str, fallback: str = DEFAULT_CHAPTER) -> str:
    clean = normalize_label(value, fallback)
    clean = strip_chapter_noise(clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"第\s*([一二三四五六七八九十百\d]+)\s*([章节讲])", r"第\1\2", clean)
    clean = re.sub(r"chapter\s*([0-9a-zA-Z_.-]+)", r"Chapter \1", clean, flags=re.I)
    clean = dedupe_repeated_phrase(clean)
    return clean


def strip_chapter_noise(value: str) -> str:
    text = normalize_label(value, "")
    noise_patterns = [
        r"\s*基础篇.*$",
        r"\s*强化篇.*$",
        r"\s*提高篇.*$",
        r"\s*冲刺篇.*$",
        r"\s*专项篇.*$",
        r"\s*微信公众号.*$",
        r"\s*公众号.*$",
        r"\s*微信.*$",
        r"\s*一研题本.*$",
        r"\s*考研.*$",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, "", text, flags=re.I)
    return text.strip()


def dedupe_repeated_phrase(value: str) -> str:
    text = normalize_label(value, "")
    if not text:
        return value
    repeated_prefix = re.match(r"^(.{2,45}?)(?:\s+\1)(?:\s+.*)?$", text)
    if repeated_prefix:
        return repeated_prefix.group(1)
    numbered = re.match(r"^((?:第\s*)?[一二三四五六七八九十百\d]+[.、章节讲]\s*[^，。；;\s]{2,30})(?:\s+\1)(?:\s+.*)?$", text)
    if numbered:
        return numbered.group(1)
    length = len(text)
    if length % 2 == 0:
        half = length // 2
        if text[:half] == text[half:]:
            return text[:half]
    compact = re.sub(r"\s+", "", text)
    for size in range(2, len(compact) // 2 + 1):
        if len(compact) % size == 0:
            unit = compact[:size]
            if unit * (len(compact) // size) == compact:
                return unit
    match = re.match(r"^(.{2,40}?)(?:\s*\1)+$", text)
    if match:
        return match.group(1)
    return text


def looks_like_chapter(text: str) -> bool:
    clean = normalize_label(text, "")
    if not clean or len(clean) > 90:
        return False
    if re.fullmatch(r"\d+|第\s*\d+\s*页|page\s*\d+", clean, flags=re.I):
        return False
    chapter_patterns = [
        r"第\s*[一二三四五六七八九十百\d]+\s*[章节讲]",
        r"(chapter|unit|lecture|section)\s*[0-9a-zA-Z_.-]+",
        r"^[一二三四五六七八九十\d]+[.、]\s*[^，。；;]{2,}",
        r"(函数|极限|积分|微分|级数|矩阵|行列式|概率|随机|网络|数据库|操作系统|组成原理|数据结构|算法)",
    ]
    return any(re.search(pattern, clean, flags=re.I) for pattern in chapter_patterns)


def extract_chapter_from_page(page: fitz.Page, text: str) -> str:
    candidates = []
    width = max(page.rect.width, 1)
    height = max(page.rect.height, 1)
    for block in page.get_text("blocks", sort=True):
        if len(block) < 5:
            continue
        x0, y0, x1, y1, block_text = block[:5]
        clean = re.sub(r"\s+", " ", str(block_text)).strip()
        if not clean:
            continue
        if y1 <= height * 0.22:
            candidates.append((0, clean))
        if x0 >= width * 0.38 and y1 <= height * 0.35:
            candidates.append((1, clean))
        if y1 <= height * 0.35 and looks_like_chapter(clean):
            candidates.append((2, clean))

    words = page.get_text("words", sort=True)
    top_words = []
    right_top_words = []
    for word in words:
        if len(word) < 5:
            continue
        x0, y0, x1, y1, word_text = word[:5]
        if y1 <= height * 0.16:
            top_words.append(str(word_text))
        if x0 >= width * 0.4 and y1 <= height * 0.32:
            right_top_words.append(str(word_text))
    for joined in (" ".join(right_top_words), " ".join(top_words)):
        joined = normalize_label(joined, "")
        if joined:
            candidates.append((3, joined))

    for _priority, candidate in sorted(candidates, key=lambda item: item[0]):
        parts = re.split(r"\s{2,}|[|｜]", candidate)
        for part in parts:
            if looks_like_chapter(part):
                return normalize_chapter(part)

    patterns = [
        r"(第[一二三四五六七八九十百\d]+[章节讲][^\n，。；;]{0,30})",
        r"((?:Chapter|Unit|Lecture|Section)\s*[\w.-]+[^\n]{0,35})",
        r"([一二三四五六七八九十\d]+[.、]\s*[^\n，。；;]{2,35})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return normalize_chapter(match.group(1), DEFAULT_CHAPTER)
    return DEFAULT_CHAPTER


def parse_ai_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("AI 返回内容不是 JSON")
    return json.loads(match.group(0))


def classify_question_locally(text: str, subject_hint: str = "", chapter_hint: str = "") -> dict:
    category, subcategory, difficulty = classify_by_rules(text)
    chapter = normalize_chapter(chapter_hint, DEFAULT_CHAPTER)
    if category == DEFAULT_CATEGORY and chapter != DEFAULT_CHAPTER:
        category = chapter
        subcategory = "章节归类"
    return {
        "subject": normalize_label(subject_hint, DEFAULT_SUBJECT),
        "chapter": chapter,
        "category": category,
        "subcategory": subcategory,
        "difficulty": difficulty,
        "reason": "导入阶段使用本地规则分类，不调用 DeepSeek。",
    }


def analyze_with_ai(question: dict) -> str:
    fallback = (
        f"知识点：{question['category']}。\n"
        f"建议先复盘这道题的核心定义、常见公式和第一步切入方法。"
        "如果是计算错误，把关键变形逐行写出；如果是方法不会，先找同类基础题练 2-3 道。"
    )
    if not os.getenv("DEEPSEEK_API_KEY"):
        return fallback + "\n\n当前未配置 DEEPSEEK_API_KEY，因此使用本地简版分析。"

    try:
        from openai import OpenAI

        prompt = f"""
你是做题集错题教练。请用中文给出简洁、可执行的错题分析。
科目：{question.get('subject', DEFAULT_SUBJECT)}
章节：{question.get('chapter', DEFAULT_CHAPTER)}
题目分类：{question['category']} / {question['subcategory']}
难度：{question['difficulty']}
做题状态：{question['status']}
错误原因：{question['mistake_reason'] or '未填写'}
我的备注：{question['user_note'] or '无'}
题目文字：
{question['ocr_text'][:3500]}

请输出：
1. 本题考察点
2. 可能错因
3. 解题切入
4. 下次练习建议
"""
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=DEEPSEEK_BASE_URL)
        result = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
        )
        return result.choices[0].message.content or fallback
    except Exception:
        print("DeepSeek analysis failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def infer_concept_hint(question: dict) -> str:
    text = f"{question.get('category', '')} {question.get('chapter', '')} {question.get('ocr_text', '')}".lower()
    rules = [
        (["洛必达", "l'h", "lhopital", "0/0", "∞/∞"], "核心定理：洛必达法则。先确认是否满足 0/0 或 ∞/∞ 型，再分别求分子分母导数。"),
        (["等价", "无穷小", "lim", "极限"], "核心定理：等价无穷小替换与极限四则运算。先判断主导项，再化简为标准极限。"),
        (["泰勒", "麦克劳林"], "核心定理：泰勒展开。优先围绕展开点保留到第一个非零项或题目所需阶数。"),
        (["级数", "收敛", "发散"], "核心定理：级数收敛判别法。先判断是正项级数、交错级数、幂级数还是一般项级数。"),
        (["积分", "原函数", "不定积分"], "核心方法：换元积分或分部积分。先观察复合函数结构与可微因子。"),
        (["微分方程", "通解", "特解"], "核心方法：一阶方程分类。先判断可分离、齐次、线性，或是否需要积分因子。"),
        (["导数", "微分", "求导"], "核心定理：复合函数求导法则。先拆外层函数与内层函数。"),
        (["矩阵", "行列式", "特征值"], "核心定理：矩阵初等变换与特征方程。先明确目标是化简、求秩还是求特征值。"),
    ]
    for keywords, hint in rules:
        if any(keyword in text for keyword in keywords):
            return hint
    return f"核心概念：{question.get('category') or DEFAULT_CATEGORY}。先回到该知识点的定义、适用条件和标准题型。"


def infer_key_step_hint(question: dict) -> str:
    text = f"{question.get('category', '')} {question.get('chapter', '')} {question.get('ocr_text', '')}".lower()
    if "洛必达" in text or "0/0" in text or "∞/∞" in text:
        return "关键第一步：把原式整理成分式极限，并验证分子、分母同时趋于 0 或同时趋于无穷，再考虑求导。"
    if "泰勒" in text or "麦克劳林" in text:
        return "关键第一步：选定展开点，写出常用展开式，例如 e^x、sin x、ln(1+x)，并判断需要保留到几阶。"
    if "级数" in text:
        return "关键第一步：先写出通项 a_n，判断是否满足 a_n -> 0；若不满足，可直接判定发散。"
    if "积分" in text:
        return "关键第一步：寻找一个可设为 u 的内层表达式，检查 du 是否能在积分式中配出来。"
    if "微分方程" in text:
        return "关键第一步：把方程整理成 y' = f(x, y) 或标准线性形式 y' + P(x)y = Q(x)。"
    if "导数" in text or "微分" in text:
        return "关键第一步：先标出外层函数，再对内层整体求导，避免漏乘链式法则中的内导数。"
    return "关键第一步：先把已知条件、要求目标和可用公式分三行写出来，再选择最直接的变形入口。"


def generate_hint_with_ai(question: dict, level: int) -> str:
    if level == 1:
        return infer_concept_hint(question)
    if level == 2:
        return infer_key_step_hint(question)

    fallback = (
        "Level 3 完整解析：\n"
        f"1. 先识别知识点：{question.get('category', DEFAULT_CATEGORY)}。\n"
        "2. 写出题目所需的核心公式。\n"
        "3. 按公式代入并逐步化简。\n\n"
        "当前未配置 DEEPSEEK_API_KEY，因此返回本地简版解析。"
    )
    if not os.getenv("DEEPSEEK_API_KEY"):
        return fallback
    try:
        from openai import OpenAI

        prompt = f"""
你是严谨的数学助教。请为下面题目生成 Level 3 Full Solution。
要求：
- 使用 Markdown + LaTeX。
- 公式用 $$...$$ 或 \\(...\\)。
- 先列关键定理，再给完整步骤，最后给易错点。
- 不要省略关键代数变形。

科目：{question.get('subject', DEFAULT_SUBJECT)}
章节：{question.get('chapter', DEFAULT_CHAPTER)}
知识点：{question.get('category', DEFAULT_CATEGORY)}
元认知错因：{', '.join(question.get('meta_tags') or []) or question.get('mistake_reason') or '未填写'}
题目文字：
{question.get('ocr_text', '')[:4000]}
"""
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=DEEPSEEK_BASE_URL)
        result = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.25,
        )
        return result.choices[0].message.content or fallback
    except Exception:
        print("DeepSeek hint failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def generate_variations_with_ai(question: dict) -> str:
    fallback = (
        "难度梯度变式：\n"
        f"Base：同属「{question.get('category', DEFAULT_CATEGORY)}」，只换数字，不换核心逻辑。\n"
        "Advanced：改变求解目标，例如由求导改为求原函数、由判定改为求参数范围。\n"
        "Pro：跨章节综合，把本题知识点与前置概念组合训练。"
    )
    if not os.getenv("DEEPSEEK_API_KEY"):
        return fallback + "\n\n当前未配置 DEEPSEEK_API_KEY，因此使用本地简版举一反三。"
    try:
        from openai import OpenAI

        prompt = f"""
你是学习训练教练。请根据错题生成“难度梯度变式”，使用 Markdown + LaTeX。
科目：{question.get('subject', DEFAULT_SUBJECT)}
章节：{question.get('chapter', DEFAULT_CHAPTER)}
知识点：{question.get('category', DEFAULT_CATEGORY)} / {question.get('subcategory', '')}
错因：{', '.join(question.get('meta_tags') or []) or question.get('mistake_reason') or '未填写'}
备注：{question.get('user_note') or '无'}
原题文字：
{question.get('ocr_text', '')[:3500]}

请输出：
1. 题型迁移规律
2. Base：换数不换逻辑，只给 1 道题
3. Advanced：变换求解目标，只给 1 道题
4. Pro：跨章节综合，只给 1 道题
5. 每道题的训练目标，不给完整答案
"""
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=DEEPSEEK_BASE_URL)
        result = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.45,
        )
        return result.choices[0].message.content or fallback
    except Exception:
        print("DeepSeek variations failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def build_reflection_payload(conn: sqlite3.Connection, period: str) -> dict:
    days = 30 if period == "month" else 7
    since_clause = f"datetime('now', '-{days} days')"
    rows = conn.execute(
        f"""
        SELECT q.*, d.title document_title, d.subject
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND datetime(q.last_reviewed_at) >= {since_clause}
        ORDER BY q.last_reviewed_at DESC
        """
    ).fetchall()
    subject_stats = conn.execute(
        f"""
        SELECT d.subject,
               COUNT(*) total,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND datetime(q.last_reviewed_at) >= {since_clause}
        GROUP BY d.subject
        ORDER BY total DESC, wrong DESC, review DESC
        """
    ).fetchall()
    chapter_stats = conn.execute(
        f"""
        SELECT d.subject, q.chapter, q.category,
               COUNT(*) total,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong,
               SUM(CASE WHEN q.status IN ('半会', '需复习') THEN 1 ELSE 0 END) review
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE q.last_reviewed_at IS NOT NULL
          AND q.status <> '未做'
          AND datetime(q.last_reviewed_at) >= {since_clause}
        GROUP BY d.subject, q.chapter, q.category
        ORDER BY wrong DESC, review DESC, total DESC
        LIMIT 18
        """
    ).fetchall()
    questions = [dict(row) for row in rows]
    wrong_questions = [q for q in questions if q["status"] in {"做错", "半会", "需复习"}]
    return {
        "period": period,
        "days": days,
        "total": len(questions),
        "correct": sum(1 for q in questions if q["status"] == "做对"),
        "wrong": sum(1 for q in questions if q["status"] == "做错"),
        "review": sum(1 for q in questions if q["status"] in {"半会", "需复习"}),
        "subjects": [dict(row) for row in subject_stats],
        "chapters": [dict(row) for row in chapter_stats],
        "wrong_questions": wrong_questions[:15],
    }


def generate_reflection_with_ai(payload: dict) -> str:
    if payload.get("force_local") or not os.getenv("DEEPSEEK_API_KEY"):
        weak = payload["chapters"][:5]
        subject_lines = "\n".join(
            f"- {item['subject']}：做题 {item['total']}，做对 {item['correct'] or 0}，做错 {item['wrong'] or 0}，需复习 {item['review'] or 0}"
            for item in payload.get("subjects", [])
        ) or "- 本周期还没有已标记的做题记录。"
        weak_lines = "\n".join(
            f"- {item['subject']} / {item['chapter']}：错题 {item['wrong'] or 0}，需复习 {item['review'] or 0}"
            for item in weak
        ) or "- 暂无明显薄弱章节。"
        return (
            f"{'本月' if payload['period'] == 'month' else '本周'}总结与反思\n"
            f"共完成/复盘 {payload['total']} 道题，做对 {payload['correct']}，做错 {payload['wrong']}，需复习 {payload['review']}。\n\n"
            "科目统计：\n"
            f"{subject_lines}\n\n"
            "当前薄弱点：\n"
            f"{weak_lines}\n\n"
            "建议：优先复盘本周期错题集中的高频章节，再补 2-3 道同章节基础题和 1 道变式题。"
        )
    try:
        from openai import OpenAI

        compact_wrong = [
            {
                "subject": q.get("subject"),
                "chapter": q.get("chapter"),
                "category": q.get("category"),
                "status": q.get("status"),
                "mistake_reason": q.get("mistake_reason"),
                "user_note": q.get("user_note"),
                "text": (q.get("ocr_text") or "")[:300],
            }
            for q in payload["wrong_questions"]
        ]
        prompt = f"""
你是学习复盘教练。请根据下面的做题记录生成中文总结与反思。
周期：{'本月' if payload['period'] == 'month' else '本周'}
统计口径：只统计本周期内被标记为做对、做错、半会或需复习的题目，不把单纯导入但未做的题目计入。
总统计：完成/复盘 {payload['total']}，做对 {payload['correct']}，做错 {payload['wrong']}，需复习 {payload['review']}
科目统计：
{json.dumps(payload.get('subjects', []), ensure_ascii=False)}
章节统计：
{json.dumps(payload['chapters'], ensure_ascii=False)}
代表性错题：
{json.dumps(compact_wrong, ensure_ascii=False)}

请输出：
1. 本周期学习内容概览，必须按科目分别说明
2. 重难点与薄弱章节
3. 错题暴露出的具体不足
4. 下个周期规划，包含优先级和练习建议
5. 需要警惕的做题习惯问题
"""
        client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=DEEPSEEK_BASE_URL)
        result = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
        )
        return result.choices[0].message.content or ""
    except Exception:
        print("DeepSeek reflection failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return generate_reflection_with_ai({**payload, "force_local": True})


def normalize_meta_tags(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        try:
            raw = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            raw = []
    return [tag for tag in raw if tag in META_TAGS]


def question_payload(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["meta_tags"] = normalize_meta_tags(item.get("meta_tags"))
    return item


def get_meta_tag_stats(conn: sqlite3.Connection, doc_id: str | None = None) -> list[dict]:
    params = []
    where = "WHERE q.status IN ('做错', '半会', '需复习')"
    if doc_id:
        where += " AND q.document_id = ?"
        params.append(doc_id)
    rows = conn.execute(f"SELECT q.meta_tags FROM questions q {where}", params).fetchall()
    counts = {tag: 0 for tag in META_TAGS}
    for row in rows:
        for tag in normalize_meta_tags(row["meta_tags"]):
            counts[tag] += 1
    max_count = max(counts.values(), default=0) or 1
    return [{"tag": tag, "count": count, "ratio": round(count / max_count, 3)} for tag, count in counts.items()]


def weak_chapter_dependencies(conn: sqlite3.Connection) -> dict[str, list[str]]:
    rows = conn.execute(
        """
        SELECT d.subject, COALESCE(NULLIF(d.title, ''), d.filename) document_title, q.document_id,
               q.chapter, q.category,
               SUM(CASE WHEN q.status = '做对' THEN 1 ELSE 0 END) correct,
               SUM(CASE WHEN q.status IN ('做对', '做错', '半会', '需复习') THEN 1 ELSE 0 END) done
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        GROUP BY d.subject, document_title, q.document_id, q.chapter, q.category
        HAVING done >= 2 AND (correct * 1.0 / done) < 0.5
        """
    ).fetchall()
    mapping: dict[str, list[str]] = {}
    for row in rows:
        deps = []
        for key in (row["category"], row["chapter"]):
            deps.extend(KNOWLEDGE_DEPENDENCIES.get(key, []))
        if deps:
            group_key = f"{row['subject'] or DEFAULT_SUBJECT} / {row['document_title'] or '做题本'}"
            mapping.setdefault(group_key, [])
            for dep in deps:
                if dep not in mapping[group_key]:
                    mapping[group_key].append(dep)
    return mapping


def find_foundation_questions(conn: sqlite3.Connection, subject: str, dependency_categories: list[str], exclude_ids: set[str]) -> list[dict]:
    if not dependency_categories:
        return []
    placeholders = ",".join("?" for _ in dependency_categories)
    params = [subject, *dependency_categories]
    rows = conn.execute(
        f"""
        SELECT q.*, d.filename, d.title document_title, d.subject
        FROM questions q
        JOIN documents d ON d.id = q.document_id
        WHERE d.subject = ?
          AND q.category IN ({placeholders})
          AND q.id NOT IN ({",".join("?" for _ in exclude_ids) if exclude_ids else "''"})
        ORDER BY
          CASE q.status WHEN '未做' THEN 0 WHEN '做对' THEN 1 ELSE 2 END,
          q.created_at ASC,
          q.page_number ASC
        LIMIT 3
        """,
        params + list(exclude_ids),
    ).fetchall()
    return [row_to_dict(row) | {"daily_kind": "foundation"} for row in rows]


def render_page_image(page: fitz.Page, image_path: Path) -> None:
    page_rect = page.rect
    target_width = 1800
    zoom = max(1.4, min(3.0, target_width / max(page_rect.width, 1)))
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False, annots=True)
    pix.save(image_path)


def extract_text_and_chapters(pdf_path: Path) -> list[dict]:
    pages = []
    last_chapter = DEFAULT_CHAPTER
    pdf = fitz.open(pdf_path)
    try:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text("text", sort=True).strip()
            extracted = extract_chapter_from_page(page, text)
            if extracted != DEFAULT_CHAPTER:
                last_chapter = extracted
            chapter = last_chapter if last_chapter != DEFAULT_CHAPTER else extracted
            pages.append({"page_number": index, "text": text, "chapter": normalize_chapter(chapter)})
    finally:
        pdf.close()
    return pages


def parse_positive_int(value: str, fallback: int | None = None) -> int | None:
    try:
        parsed = int(str(value).strip())
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def import_pdf(
    filename: str,
    pdf_bytes: bytes,
    title: str = "",
    subject: str = "",
    start_page: int | None = None,
    end_page: int | None = None,
) -> dict:
    doc_id = uuid.uuid4().hex
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "questions.pdf"
    pdf_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    pdf_path.write_bytes(pdf_bytes)
    title = title.strip() or Path(filename).stem
    subject = normalize_label(subject, DEFAULT_SUBJECT)

    now = datetime.now().isoformat(timespec="seconds")
    inserted = []
    pdf = fitz.open(pdf_path)
    last_chapter = DEFAULT_CHAPTER
    try:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (id, title, subject, filename, stored_path, page_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, title, subject, filename, str(pdf_path), pdf.page_count, now),
            )
            page_start = max(start_page or 1, 1)
            page_end = min(end_page or pdf.page_count, pdf.page_count)
            if page_start > page_end:
                raise ValueError("页码范围无效，请检查起止页。")
            for index in range(page_start, page_end + 1):
                page = pdf[index - 1]
                q_id = uuid.uuid4().hex
                text = page.get_text("text", sort=True).strip()
                extracted_chapter = extract_chapter_from_page(page, text)
                if extracted_chapter != DEFAULT_CHAPTER:
                    last_chapter = extracted_chapter
                chapter_hint = last_chapter if last_chapter != DEFAULT_CHAPTER else extracted_chapter
                image_path = PAGE_DIR / f"{doc_id}_page_{index:03d}.png"
                render_page_image(page, image_path)
                classification = classify_question_locally(text, subject, chapter_hint)
                conn.execute(
                    """
                    INSERT INTO questions (
                        id, document_id, page_number, image_path, ocr_text, category,
                        subcategory, chapter, difficulty, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q_id,
                        doc_id,
                        index,
                        str(image_path),
                        text,
                        classification["category"],
                        classification["subcategory"],
                        classification["chapter"],
                        classification["difficulty"],
                        now,
                    ),
                )
                inserted.append(
                    {
                        "id": q_id,
                        "page_number": index,
                        "category": classification["category"],
                        "subcategory": classification["subcategory"],
                        "chapter": classification["chapter"],
                    }
                )
    finally:
        pdf.close()

    return {
        "document_id": doc_id,
        "title": title,
        "subject": subject,
        "filename": filename,
        "page_count": len(inserted),
        "questions": inserted,
    }


def unlink_if_inside_data(path_value: str) -> None:
    if not path_value:
        return
    path = Path(path_value).resolve()
    if str(path).startswith(str(DATA_DIR.resolve())) and path.exists() and path.is_file():
        path.unlink()


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "GaoshuDemo/0.1"

    def log_message(self, format: str, *args) -> None:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                return self.serve_file(STATIC_DIR / "index.html")
            if parsed.path == "/api/health":
                return json_response(self, {"ok": True, "date": date.today().isoformat()})
            if parsed.path == "/api/documents":
                return self.handle_documents()
            if parsed.path.startswith("/api/documents/") and parsed.path.endswith("/chapter-stats"):
                doc_id = parsed.path.split("/")[-2]
                return self.handle_chapter_stats(doc_id)
            if parsed.path == "/api/questions":
                return self.handle_questions(parse_qs(parsed.query))
            if parsed.path == "/api/daily":
                return self.handle_daily()
            if parsed.path == "/api/reflection":
                return self.handle_reflection_preview(parse_qs(parsed.query))
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_question_detail(q_id)
            if parsed.path.startswith("/static/") or parsed.path.startswith("/data/"):
                return self.serve_file(ROOT / parsed.path.lstrip("/"))
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/upload":
                return self.handle_upload()
            if parsed.path.startswith("/api/documents/") and parsed.path.endswith("/rescan-chapters"):
                doc_id = parsed.path.split("/")[-2]
                return self.handle_rescan_chapters(doc_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/analyze"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_analyze(q_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/hint"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_hint(q_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/variations"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_variations(q_id)
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/crop"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_crop_question(q_id)
            if parsed.path == "/api/reflection":
                return self.handle_reflection()
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/documents/"):
                doc_id = parsed.path.split("/")[-1]
                return self.handle_delete_document(doc_id)
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_delete_question(q_id)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def do_PATCH(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/questions/"):
                q_id = parsed.path.split("/")[-1]
                return self.handle_update_question(q_id)
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            return json_response(self, {"error": str(exc)}, 500)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def serve_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not str(resolved).startswith(str(ROOT)) or not resolved.exists() or resolved.is_dir():
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)
        content_types = {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".pdf": "application/pdf",
        }
        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(resolved.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_upload(self) -> None:
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        file_item = form["file"] if "file" in form else None
        if file_item is None or not file_item.filename:
            return json_response(self, {"error": "请上传 PDF 文件。"}, 400)
        if not file_item.filename.lower().endswith(".pdf"):
            return json_response(self, {"error": "当前 demo 只支持 PDF。"}, 400)
        title = form.getfirst("title", "")
        subject = form.getfirst("subject", "")
        start_page = parse_positive_int(form.getfirst("start_page", ""), None)
        end_page = parse_positive_int(form.getfirst("end_page", ""), None)
        result = import_pdf(file_item.filename, file_item.file.read(), title, subject, start_page, end_page)
        return json_response(self, result)

    def handle_documents(self) -> None:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT d.*,
                       COUNT(q.id) question_count,
                       SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong_count,
                       SUM(CASE WHEN q.status IN ('需复习', '半会') THEN 1 ELSE 0 END) review_count
                FROM documents d
                LEFT JOIN questions q ON q.document_id = d.id
                GROUP BY d.id
                ORDER BY d.created_at DESC
                """
            ).fetchall()
            options = get_filter_options(conn)
        return json_response(self, {"documents": [document_to_dict(row) for row in rows], **options})

    def handle_questions(self, query: dict) -> None:
        where, params = build_question_filters(
            query,
            ("category", "status", "document_id", "chapter", "subject", "search"),
        )
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT q.*, d.filename, d.title document_title, d.subject
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                {where}
                ORDER BY q.created_at DESC, q.page_number ASC
                """,
                params,
            ).fetchall()
            stats = conn.execute(
                """
                SELECT q.category, COUNT(*) total,
                       SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                {where}
                GROUP BY q.category
                ORDER BY total DESC
                """.format(where=where),
                params,
            ).fetchall()
            subject_stats = conn.execute(
                """
                SELECT d.subject, COUNT(*) total,
                       SUM(CASE WHEN q.status = '做错' THEN 1 ELSE 0 END) wrong
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                GROUP BY d.subject
                ORDER BY total DESC
                """
            ).fetchall()
            options = get_scoped_filter_options(conn, query)
        return json_response(
            self,
            {
                "questions": [row_to_dict(row) for row in rows],
                "stats": [dict(row) for row in stats],
                "subject_stats": [dict(row) for row in subject_stats],
                **options,
            },
        )

    def handle_question_detail(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.filename, d.title document_title, d.subject
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
        if not row:
            return json_response(self, {"error": "题目不存在。"}, 404)
        return json_response(self, row_to_dict(row))

    def handle_delete_question(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT image_path FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            unlink_if_inside_data(row["image_path"])
            conn.execute("DELETE FROM questions WHERE id = ?", (q_id,))
        return json_response(self, {"ok": True})

    def handle_delete_document(self, doc_id: str) -> None:
        with connect() as conn:
            doc = conn.execute("SELECT stored_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            question_rows = conn.execute("SELECT image_path FROM questions WHERE document_id = ?", (doc_id,)).fetchall()
            for row in question_rows:
                unlink_if_inside_data(row["image_path"])
            unlink_if_inside_data(doc["stored_path"])
            conn.execute("DELETE FROM questions WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return json_response(self, {"ok": True})

    def handle_rescan_chapters(self, doc_id: str) -> None:
        with connect() as conn:
            doc = conn.execute("SELECT stored_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            pdf_path = Path(doc["stored_path"])
            if not pdf_path.exists():
                return json_response(self, {"error": "原始 PDF 文件不存在，无法重扫。"}, 404)
            pages = extract_text_and_chapters(pdf_path)
            updated = 0
            for page in pages:
                category, subcategory, difficulty = classify_by_rules(page["text"])
                if category == DEFAULT_CATEGORY and page["chapter"] != DEFAULT_CHAPTER:
                    category = page["chapter"]
                    subcategory = "章节归类"
                cursor = conn.execute(
                    """
                    UPDATE questions
                    SET ocr_text = ?, chapter = ?, category = ?, subcategory = ?, difficulty = ?
                    WHERE document_id = ? AND page_number = ?
                    """,
                    (
                        page["text"],
                        page["chapter"],
                        category,
                        subcategory,
                        difficulty,
                        doc_id,
                        page["page_number"],
                    ),
                )
                updated += max(cursor.rowcount, 0)
        return json_response(self, {"ok": True, "pages": len(pages), "updated": updated})

    def handle_update_question(self, q_id: str) -> None:
        payload = self.read_json()
        allowed = {"status", "mistake_reason", "meta_tags", "user_note", "category", "subcategory", "chapter", "difficulty"}
        updates = {k: v for k, v in payload.items() if k in allowed}
        if not updates:
            return json_response(self, {"error": "没有可更新字段。"}, 400)
        with connect() as conn:
            current = conn.execute("SELECT * FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not current:
                return json_response(self, {"error": "题目不存在。"}, 404)
            if "meta_tags" in updates:
                updates["meta_tags"] = json.dumps(normalize_meta_tags(updates["meta_tags"]), ensure_ascii=False)
            if updates.get("status") in WRONGISH_STATUSES:
                existing_tags = normalize_meta_tags(updates.get("meta_tags", current["meta_tags"]))
                if not existing_tags:
                    return json_response(self, {"error": "标记错题前，请至少选择一个元认知错因标签。"}, 400)
            if updates.get("status") in {*WRONGISH_STATUSES, "做对"}:
                updates["last_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
                updates["review_count"] = "review_count + 1"
                updates.update(schedule_for_status(current, updates["status"]))
            assignments = []
            params = []
            for key, value in updates.items():
                if key == "review_count":
                    assignments.append("review_count = review_count + 1")
                else:
                    assignments.append(f"{key} = ?")
                    params.append(value)
            params.append(q_id)
            conn.execute(f"UPDATE questions SET {', '.join(assignments)} WHERE id = ?", params)
            row = conn.execute("SELECT q.*, '' filename FROM questions q WHERE id = ?", (q_id,)).fetchone()
        return json_response(self, row_to_dict(row))

    def handle_analyze(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.subject
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            analysis = analyze_with_ai(question_payload(row))
            conn.execute("UPDATE questions SET ai_analysis = ? WHERE id = ?", (analysis, q_id))
        return json_response(self, {"ai_analysis": analysis})

    def handle_hint(self, q_id: str) -> None:
        payload = self.read_json()
        level = parse_positive_int(str(payload.get("level", "1")), 1) or 1
        level = max(1, min(3, level))
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.subject
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            hint = generate_hint_with_ai(question_payload(row), level)
            conn.execute("UPDATE questions SET ai_hint = ? WHERE id = ?", (hint, q_id))
        return json_response(self, {"level": level, "hint": hint})

    def handle_variations(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                """
                SELECT q.*, d.subject
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.id = ?
                """,
                (q_id,),
            ).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            variations = generate_variations_with_ai(question_payload(row))
            conn.execute("UPDATE questions SET ai_variations = ? WHERE id = ?", (variations, q_id))
        return json_response(self, {"ai_variations": variations})

    def handle_crop_question(self, q_id: str) -> None:
        payload = self.read_json()
        crop = payload.get("crop") or {}
        with connect() as conn:
            row = conn.execute("SELECT image_path FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            image_path = Path(row["image_path"])
            if not image_path.exists():
                return json_response(self, {"error": "题图文件不存在。"}, 404)
            try:
                from PIL import Image

                with Image.open(image_path) as image:
                    width, height = image.size
                    left = max(0, min(width - 1, int(float(crop.get("x", 0)) * width)))
                    top = max(0, min(height - 1, int(float(crop.get("y", 0)) * height)))
                    right = max(left + 1, min(width, int(float(crop.get("w", 1)) * width) + left))
                    bottom = max(top + 1, min(height, int(float(crop.get("h", 1)) * height) + top))
                    cropped = image.crop((left, top, right, bottom))
                    cropped.save(image_path)
            except ImportError:
                return json_response(self, {"error": "裁剪功能需要安装 Pillow：pip install -r requirements.txt"}, 500)
            except Exception as exc:
                return json_response(self, {"error": f"裁剪失败：{exc}"}, 400)
            updated = conn.execute("SELECT q.*, '' filename FROM questions q WHERE id = ?", (q_id,)).fetchone()
        return json_response(self, row_to_dict(updated))

    def handle_chapter_stats(self, doc_id: str) -> None:
        with connect() as conn:
            doc = conn.execute("SELECT id, title, filename FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not doc:
                return json_response(self, {"error": "做题本不存在。"}, 404)
            rows = conn.execute(
                """
                SELECT chapter,
                       MIN(page_number) first_page,
                       COUNT(*) total,
                       SUM(CASE WHEN status = '做对' THEN 1 ELSE 0 END) correct,
                       SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong,
                       SUM(CASE WHEN status IN ('半会', '需复习') THEN 1 ELSE 0 END) review,
                       SUM(CASE WHEN status = '未做' THEN 1 ELSE 0 END) todo
                FROM questions
                WHERE document_id = ?
                GROUP BY chapter
                ORDER BY first_page ASC
                """,
                (doc_id,),
            ).fetchall()
            meta_stats = get_meta_tag_stats(conn, doc_id)
        stats = []
        for row in rows:
            done = (row["correct"] or 0) + (row["wrong"] or 0) + (row["review"] or 0)
            correct_rate = round(((row["correct"] or 0) / done) * 100, 1) if done else 0
            item = dict(row)
            item["correct_rate"] = correct_rate
            stats.append(item)
        return json_response(self, {"document": document_to_dict(doc), "chapters": stats, "meta_tags": meta_stats})

    def handle_reflection_preview(self, query: dict) -> None:
        period = query.get("period", ["week"])[0]
        if period not in {"week", "month"}:
            period = "week"
        with connect() as conn:
            payload = build_reflection_payload(conn, period)
        return json_response(self, payload)

    def handle_reflection(self) -> None:
        payload = self.read_json()
        period = payload.get("period", "week")
        if period not in {"week", "month"}:
            period = "week"
        with connect() as conn:
            reflection_payload = build_reflection_payload(conn, period)
        reflection = generate_reflection_with_ai(reflection_payload)
        return json_response(self, {"reflection": reflection, "summary": reflection_payload})

    def handle_daily(self) -> None:
        today = date.today().isoformat()
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT q.*, d.filename, d.title document_title, d.subject
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                WHERE q.status IN ('做错', '需复习', '半会')
                   OR (
                       q.ever_wrong = 1
                       AND q.mastered_at IS NULL
                       AND q.next_review_at IS NOT NULL
                       AND date(q.next_review_at) <= date(?)
                   )
                ORDER BY
                    d.subject ASC,
                    COALESCE(NULLIF(d.title, ''), d.filename) ASC,
                    CASE q.status
                        WHEN '做错' THEN 0
                        WHEN '需复习' THEN 1
                        WHEN '半会' THEN 2
                        WHEN '做对' THEN 3
                        ELSE 4
                    END,
                    q.review_stage ASC,
                    COALESCE(q.next_review_at, q.last_reviewed_at, q.created_at) ASC
                """
                ,
                (today,),
            ).fetchall()
            dependency_map = weak_chapter_dependencies(conn)
        groups_map: dict[str, dict] = {}
        used_ids: set[str] = set()
        for row in rows:
            item = row_to_dict(row)
            item["daily_kind"] = "review"
            used_ids.add(item["id"])
            book_name = item.get("document_title") or item.get("filename") or "做题本"
            group_key = f"{item.get('subject') or DEFAULT_SUBJECT} / {book_name}"
            if group_key not in groups_map:
                groups_map[group_key] = {"title": group_key, "questions": []}
            if len(groups_map[group_key]["questions"]) < 4:
                groups_map[group_key]["questions"].append(item)
        with connect() as conn:
            for group_key, dependencies in dependency_map.items():
                if group_key not in groups_map:
                    continue
                subject = group_key.split(" / ", 1)[0]
                if len(groups_map[group_key]["questions"]) >= 5:
                    continue
                foundations = find_foundation_questions(conn, subject, dependencies, used_ids)
                if foundations:
                    groups_map[group_key]["questions"].append(foundations[0])
                    used_ids.add(foundations[0]["id"])
        groups = [group for group in groups_map.values() if group["questions"]]
        return json_response(
            self,
            {
                "date": date.today().isoformat(),
                "groups": groups,
                "plan": [question for group in groups for question in group["questions"]],
                "message": "每日练习由当前错题、到期复习题和低正确率章节的前置基础题组成；每组最多 5 道，其中约 20% 用于补基础。",
            },
        )


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), DemoHandler)
    print(f"Gaoshu demo running at http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
