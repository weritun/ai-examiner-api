import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import hashlib
from datetime import datetime

app = FastAPI(title="AI Examiner Server")

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Фейковая база данных в памяти
users_db = {
    "admin": {
        "id": 1,
        "username": "admin",
        "password_hash": hashlib.sha256("admin".encode()).hexdigest(),
        "role": "admin"
    }
}
checks_db = []
next_user_id = 2
next_check_id = 1

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

@app.get("/")
def root():
    return {"status": "ok", "message": "AI Examiner Server is running"}

@app.get("/health")
def health():
    return {"status": "ok", "users": len(users_db), "checks": len(checks_db)}

@app.post("/login")
def login(req: AuthRequest):
    print(f"Login attempt: {req.username}")
    user = users_db.get(req.username)
    if user and user["password_hash"] == hash_password(req.password):
        print(f"Login success: {req.username}")
        return {
            "status": "ok",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"]
            }
        }
    print(f"Login failed: {req.username}")
    raise HTTPException(status_code=401, detail="Неверный логин или пароль")

@app.post("/register")
def register(req: AuthRequest):
    global next_user_id
    print(f"Register attempt: {req.username}")
    
    if req.username in users_db:
        raise HTTPException(status_code=400, detail="Пользователь уже существует")
    
    users_db[req.username] = {
        "id": next_user_id,
        "username": req.username,
        "password_hash": hash_password(req.password),
        "role": "user"
    }
    next_user_id += 1
    print(f"User registered: {req.username}")
    return {"status": "ok"}

@app.post("/save_check")
def save_check(data: CheckSaveRequest):
    global next_check_id
    check = {
        "id": next_check_id,
        "username": data.username,
        "archive_name": data.archive_name,
        "files_count": data.files_count,
        "result_text": data.result_text,
        "score": data.score,
        "checked_at": datetime.now().isoformat()
    }
    checks_db.append(check)
    next_check_id += 1
    print(f"Saved check: {data.archive_name} for {data.username}")
    return {"status": "saved", "check_id": check["id"]}

@app.get("/history/{username}")
def get_history(username: str):
    user_checks = [c for c in checks_db if c["username"] == username]
    if username == "admin":
        user_checks = checks_db
    
    result = []
    for check in user_checks:
        result.append({
            "check_id": check["id"],
            "archive_name": check["archive_name"],
            "files_count": check["files_count"],
            "result_text": check["result_text"],
            "score": check["score"],
            "date": check["checked_at"],
            "result_preview": check["result_text"][:200] + "..." if len(check["result_text"]) > 200 else check["result_text"],
            "full_result": check["result_text"],
            "username": check["username"]
        })
    return result

@app.delete("/delete_item")
def delete_item(req: DeleteItemRequest):
    global checks_db
    if req.table_name == 'checks':
        checks_db = [c for c in checks_db if c["id"] != req.item_id]
        return {"status": "deleted"}
    raise HTTPException(status_code=400, detail="Invalid table name")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
