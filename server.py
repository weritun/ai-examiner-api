import os
import uvicorn
import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import hashlib

# ======================================================
# НАСТРОЙКИ ПОДКЛЮЧЕНИЯ К SUPABASE
# ======================================================
SUPABASE_HOST = "aws-0-eu-central-1.pooler.supabase.com"
SUPABASE_PORT = "5432"
SUPABASE_DB = "postgres"
SUPABASE_USER = "postgres"
# Пароль будет взят из переменной окружения на Render
SUPABASE_PASSWORD = os.environ.get("SUPABASE_PASSWORD", "")

DB_CONFIG = {
    "dbname": SUPABASE_DB,
    "user": SUPABASE_USER,
    "password": SUPABASE_PASSWORD,
    "host": SUPABASE_HOST,
    "port": SUPABASE_PORT
}

app = FastAPI(title="AI Examiner Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

class AuthRequest(BaseModel):
    username: str
    password: str

class CheckSaveRequest(BaseModel):
    username: str
    archive_name: str
    files_count: int
    result_text: str
    score: Optional[str] = None

class DeleteItemRequest(BaseModel):
    item_id: int
    table_name: str

def get_conn():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print("Ошибка подключения к Supabase:", e)
        raise HTTPException(status_code=500, detail=f"DB Error: {str(e)}")

@app.get("/")
def root():
    return {"status": "ok", "message": "AI Examiner Server is running"}

@app.post("/login")
def login(req: AuthRequest):
    conn = get_conn()
    cur = conn.cursor()
    pwd_hash = hash_password(req.password)
    cur.execute(
        "SELECT ID_Users, username, role FROM users WHERE username = %s AND password_hash = %s",
        (req.username, pwd_hash)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        return {"status": "ok", "user": {"id": user[0], "username": user[1], "role": user[2]}}
    raise HTTPException(status_code=401, detail="Неверный логин или пароль")

@app.post("/register")
def register(req: AuthRequest):
    conn = get_conn()
    cur = conn.cursor()
    try:
        pwd_hash = hash_password(req.password)
        cur.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'user')",
            (req.username, pwd_hash)
        )
        conn.commit()
        return {"status": "ok"}
    except psycopg2.IntegrityError:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    finally:
        cur.close()
        conn.close()

@app.post("/save_check")
def save_check(data: CheckSaveRequest):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT ID_Users FROM users WHERE username = %s", (data.username,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        user_id = row[0]
        cur.execute("""
            INSERT INTO projects (ID_Users, archive_name, files_count)
            VALUES (%s, %s, %s) RETURNING ID_Projects
        """, (user_id, data.archive_name, data.files_count))
        project_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO checks (ID_Projects, result_text, score)
            VALUES (%s, %s, %s)
        """, (project_id, data.result_text, data.score))
        conn.commit()
        return {"status": "saved"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@app.get("/history/{username}")
def get_history(username: str):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT role FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        is_admin = (row[0] == 'admin')
        if is_admin:
            cur.execute("""
                SELECT c.ID_Checks as check_id,
                       p.archive_name,
                       p.files_count,
                       c.result_text,
                       c.score,
                       c.checked_at,
                       u.username
                FROM checks c
                JOIN projects p ON c.ID_Projects = p.ID_Projects
                JOIN users u ON p.ID_Users = u.ID_Users
                ORDER BY c.checked_at DESC
            """)
        else:
            cur.execute("""
                SELECT c.ID_Checks as check_id,
                       p.archive_name,
                       p.files_count,
                       c.result_text,
                       c.score,
                       c.checked_at,
                       u.username
                FROM checks c
                JOIN projects p ON c.ID_Projects = p.ID_Projects
                JOIN users u ON p.ID_Users = u.ID_Users
                WHERE u.username = %s
                ORDER BY c.checked_at DESC
            """, (username,))
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        result = []
        for row in rows:
            item = dict(zip(columns, row))
            if item.get('checked_at'):
                item['date'] = str(item['checked_at'])
            full_text = item.get('result_text', '') or ''
            item['result_preview'] = (full_text[:200] + "...") if len(full_text) > 200 else full_text
            item['full_result'] = full_text
            result.append(item)
        return result
    finally:
        cur.close()
        conn.close()

@app.delete("/delete_item")
def delete_item(req: DeleteItemRequest):
    conn = get_conn()
    cur = conn.cursor()
    try:
        if req.table_name == 'checks':
            cur.execute("DELETE FROM checks WHERE ID_Checks = %s", (req.item_id,))
        elif req.table_name == 'projects':
            cur.execute("DELETE FROM projects WHERE ID_Projects = %s", (req.item_id,))
        else:
            raise HTTPException(status_code=400, detail="Invalid table name")
        conn.commit()
        return {"status": "deleted"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)