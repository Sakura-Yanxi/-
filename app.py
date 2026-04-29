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
from datetime import date, datetime
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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

CATEGORIES = [
    "函数、极限与连续",
    "导数与微分",
    "微分中值定理",
    "导数应用",
    "不定积分",
    "定积分及其应用",
    "多元函数微分学",
    "重积分",
    "无穷级数",
    "微分方程",
    "向量代数与空间解析几何",
    "综合题",
]

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
                difficulty TEXT NOT NULL DEFAULT '中等',
                status TEXT NOT NULL DEFAULT '未做',
                mistake_reason TEXT NOT NULL DEFAULT '',
                user_note TEXT NOT NULL DEFAULT '',
                ai_analysis TEXT NOT NULL DEFAULT '',
                review_count INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            """
        )


def to_public_path(path: str | Path) -> str:
    absolute = Path(path).resolve()
    return "/" + absolute.relative_to(ROOT).as_posix()


def row_to_dict(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["image_url"] = to_public_path(item["image_path"])
    return item


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
    return "综合题", "待人工确认", "中等"


def parse_ai_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, flags=re.S)
    if not match:
        raise ValueError("AI 返回内容不是 JSON")
    return json.loads(match.group(0))


def call_openai_for_question(text: str, image_path: Path | None = None) -> dict | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI

        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    "你是高等数学题库整理助手。请根据题目内容归类。"
                    f"可选一级分类：{', '.join(CATEGORIES)}。"
                    "只返回 JSON，不要 Markdown。字段：category, subcategory, difficulty, reason。"
                    f"\n题目文字：{text[:3500]}"
                ),
            }
        ]
        if image_path and image_path.exists():
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                }
            )

        client = OpenAI()
        result = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=0.2,
        )
        parsed = parse_ai_json(result.choices[0].message.content or "")
        if parsed.get("category") not in CATEGORIES:
            parsed["category"] = "综合题"
        return parsed
    except Exception:
        print("OpenAI classify failed; falling back to rules", file=sys.stderr)
        traceback.print_exc()
        return None


def classify_question(text: str, image_path: Path | None = None) -> dict:
    ai = call_openai_for_question(text, image_path)
    if ai:
        return {
            "category": ai.get("category", "综合题"),
            "subcategory": ai.get("subcategory", "AI 分类"),
            "difficulty": ai.get("difficulty", "中等"),
            "reason": ai.get("reason", ""),
        }
    category, subcategory, difficulty = classify_by_rules(text)
    return {
        "category": category,
        "subcategory": subcategory,
        "difficulty": difficulty,
        "reason": "未配置 OPENAI_API_KEY，已使用本地关键词规则分类。",
    }


def analyze_with_ai(question: dict) -> str:
    fallback = (
        f"知识点：{question['category']}。\n"
        f"建议先复盘这道题的核心定义、常见公式和第一步切入方法。"
        "如果是计算错误，把关键变形逐行写出；如果是方法不会，先找同类基础题练 2-3 道。"
    )
    if not os.getenv("OPENAI_API_KEY"):
        return fallback + "\n\n当前未配置 OPENAI_API_KEY，因此使用本地简版分析。"

    try:
        from openai import OpenAI

        prompt = f"""
你是高等数学错题教练。请用中文给出简洁、可执行的错题分析。
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
        client = OpenAI()
        result = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.35,
        )
        return result.choices[0].message.content or fallback
    except Exception:
        print("OpenAI analysis failed; falling back", file=sys.stderr)
        traceback.print_exc()
        return fallback


def import_pdf(filename: str, pdf_bytes: bytes) -> dict:
    doc_id = uuid.uuid4().hex
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "questions.pdf"
    pdf_path = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    pdf_path.write_bytes(pdf_bytes)

    now = datetime.now().isoformat(timespec="seconds")
    inserted = []
    pdf = fitz.open(pdf_path)
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, stored_path, page_count, created_at) VALUES (?, ?, ?, ?, ?)",
                (doc_id, filename, str(pdf_path), pdf.page_count, now),
            )
            for index, page in enumerate(pdf, start=1):
                q_id = uuid.uuid4().hex
                text = page.get_text("text").strip()
                pix = page.get_pixmap(matrix=fitz.Matrix(1.7, 1.7), alpha=False)
                image_path = PAGE_DIR / f"{doc_id}_page_{index:03d}.png"
                pix.save(image_path)
                classification = classify_question(text, image_path)
                conn.execute(
                    """
                    INSERT INTO questions (
                        id, document_id, page_number, image_path, ocr_text, category,
                        subcategory, difficulty, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q_id,
                        doc_id,
                        index,
                        str(image_path),
                        text,
                        classification["category"],
                        classification["subcategory"],
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
                    }
                )
    finally:
        pdf.close()

    return {"document_id": doc_id, "filename": filename, "page_count": len(inserted), "questions": inserted}


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
            if parsed.path == "/api/questions":
                return self.handle_questions(parse_qs(parsed.query))
            if parsed.path == "/api/daily":
                return self.handle_daily()
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
            if parsed.path.startswith("/api/questions/") and parsed.path.endswith("/analyze"):
                q_id = parsed.path.split("/")[-2]
                return self.handle_analyze(q_id)
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
        result = import_pdf(file_item.filename, file_item.file.read())
        return json_response(self, result)

    def handle_questions(self, query: dict) -> None:
        clauses = []
        params: list[str] = []
        for key in ("category", "status"):
            value = query.get(key, [""])[0]
            if value:
                clauses.append(f"{key} = ?")
                params.append(value)
        search = query.get("search", [""])[0].strip()
        if search:
            clauses.append("(ocr_text LIKE ? OR subcategory LIKE ? OR user_note LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with connect() as conn:
            rows = conn.execute(
                f"""
                SELECT q.*, d.filename
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                {where}
                ORDER BY q.created_at DESC, q.page_number ASC
                """,
                params,
            ).fetchall()
            stats = conn.execute(
                """
                SELECT category, COUNT(*) total,
                       SUM(CASE WHEN status = '做错' THEN 1 ELSE 0 END) wrong
                FROM questions
                GROUP BY category
                ORDER BY total DESC
                """
            ).fetchall()
        return json_response(
            self,
            {
                "questions": [row_to_dict(row) for row in rows],
                "stats": [dict(row) for row in stats],
                "categories": CATEGORIES,
            },
        )

    def handle_question_detail(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute(
                "SELECT q.*, d.filename FROM questions q JOIN documents d ON d.id = q.document_id WHERE q.id = ?",
                (q_id,),
            ).fetchone()
        if not row:
            return json_response(self, {"error": "题目不存在。"}, 404)
        return json_response(self, row_to_dict(row))

    def handle_update_question(self, q_id: str) -> None:
        payload = self.read_json()
        allowed = {"status", "mistake_reason", "user_note", "category", "subcategory", "difficulty"}
        updates = {k: v for k, v in payload.items() if k in allowed}
        if not updates:
            return json_response(self, {"error": "没有可更新字段。"}, 400)
        if updates.get("status") in {"做错", "半会", "需复习", "做对"}:
            updates["last_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
            updates["review_count"] = "review_count + 1"
        assignments = []
        params = []
        for key, value in updates.items():
            if key == "review_count":
                assignments.append("review_count = review_count + 1")
            else:
                assignments.append(f"{key} = ?")
                params.append(value)
        params.append(q_id)
        with connect() as conn:
            conn.execute(f"UPDATE questions SET {', '.join(assignments)} WHERE id = ?", params)
            row = conn.execute("SELECT q.*, '' filename FROM questions q WHERE id = ?", (q_id,)).fetchone()
        if not row:
            return json_response(self, {"error": "题目不存在。"}, 404)
        return json_response(self, row_to_dict(row))

    def handle_analyze(self, q_id: str) -> None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM questions WHERE id = ?", (q_id,)).fetchone()
            if not row:
                return json_response(self, {"error": "题目不存在。"}, 404)
            analysis = analyze_with_ai(dict(row))
            conn.execute("UPDATE questions SET ai_analysis = ? WHERE id = ?", (analysis, q_id))
        return json_response(self, {"ai_analysis": analysis})

    def handle_daily(self) -> None:
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT q.*, d.filename
                FROM questions q
                JOIN documents d ON d.id = q.document_id
                ORDER BY
                    CASE q.status
                        WHEN '做错' THEN 0
                        WHEN '需复习' THEN 1
                        WHEN '半会' THEN 2
                        WHEN '未做' THEN 3
                        ELSE 4
                    END,
                    COALESCE(q.last_reviewed_at, q.created_at) ASC
                LIMIT 8
                """
            ).fetchall()
        return json_response(
            self,
            {
                "date": date.today().isoformat(),
                "plan": [row_to_dict(row) for row in rows],
                "message": "优先复习错题和需复习题，再补未做题。建议今天完成 5-8 道。",
            },
        )


def main() -> None:
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), DemoHandler)
    print(f"Gaoshu demo running at http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
