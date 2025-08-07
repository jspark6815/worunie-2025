#!/usr/bin/env python3
"""
DB 조회 웹 인터페이스
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
from datetime import datetime
import os

app = FastAPI(title="DB Viewer")

# 템플릿 설정
templates = Jinja2Templates(directory="templates")

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect('teams.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("db_viewer.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
async def view_users(request: Request):
    """사용자 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, name, school_major, position, insurance, email, created_at
        FROM users 
        WHERE is_active = 1 
        ORDER BY name
    """)
    
    users = cursor.fetchall()
    conn.close()
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "total_users": len(users)
    })

@app.get("/users/add", response_class=HTMLResponse)
async def add_user_form(request: Request):
    """사용자 등록 폼"""
    return templates.TemplateResponse("user_form.html", {
        "request": request,
        "user": None,
        "action": "add"
    })

@app.post("/users/add", response_class=HTMLResponse)
async def add_user(request: Request):
    """사용자 등록"""
    # 폼 데이터를 직접 파싱
    form_data = await request.form()
    
    # 디버깅을 위한 로그
    print(f"DEBUG: Form data received: {dict(form_data)}")
    
    # 필수 필드 추출
    name = form_data.get("name", "")
    user_id = form_data.get("user_id", "")
    school_major = form_data.get("school_major", "")
    position = form_data.get("position", "")
    insurance = form_data.get("insurance", "")
    email = form_data.get("email", "")
    
    # 필수 필드 검증
    if not name:
        raise HTTPException(status_code=400, detail="이름은 필수 입력 항목입니다")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # user_id가 비어있거나 'U'로 시작하지 않으면 임시 ID 생성
        if not user_id or not user_id.startswith('U'):
            user_id = f"temp_{datetime.now().timestamp()}"
        
        cursor.execute("""
            INSERT INTO users (user_id, name, school_major, position, insurance, email, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (user_id, name, school_major, position, insurance, email, datetime.now()))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"DEBUG: Error in add_user - {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/users/edit/{user_id}", response_class=HTMLResponse)
async def edit_user_form(request: Request, user_id: str):
    """사용자 수정 폼"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, name, school_major, position, insurance, email
        FROM users 
        WHERE user_id = ? AND is_active = 1
    """, (user_id,))
    
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    
    return templates.TemplateResponse("user_form.html", {
        "request": request,
        "user": user,
        "action": "edit"
    })

@app.post("/users/edit/{user_id}", response_class=HTMLResponse)
async def edit_user(request: Request, user_id: str,
                   name: str = Form(...),
                   new_user_id: str = Form(...),
                   school_major: str = Form(...),
                   position: str = Form(...),
                   insurance: str = Form(...),
                   email: str = Form(...)):
    """사용자 수정"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # new_user_id가 비어있거나 'U'로 시작하지 않으면 기존 ID 유지
        if not new_user_id or not new_user_id.startswith('U'):
            new_user_id = user_id
        
        cursor.execute("""
            UPDATE users 
            SET user_id = ?, name = ?, school_major = ?, position = ?, insurance = ?, email = ?
            WHERE user_id = ? AND is_active = 1
        """, (new_user_id, name, school_major, position, insurance, email, user_id))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/users/delete/{user_id}", response_class=HTMLResponse)
async def delete_user(request: Request, user_id: str):
    """사용자 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE users 
            SET is_active = 0
            WHERE user_id = ?
        """, (user_id,))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/users/quick-edit-slack-id/{user_id}", response_class=HTMLResponse)
async def quick_edit_slack_id(request: Request, user_id: str, new_user_id: str = Form(...)):
    """빠른 Slack ID 변경"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # new_user_id가 비어있거나 'U'로 시작하지 않으면 오류
        if not new_user_id or not new_user_id.startswith('U'):
            raise HTTPException(status_code=400, detail="Slack ID는 'U'로 시작해야 합니다")
        
        cursor.execute("""
            UPDATE users 
            SET user_id = ?
            WHERE user_id = ? AND is_active = 1
        """, (new_user_id, user_id))
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/teams", response_class=HTMLResponse)
async def view_teams(request: Request):
    """팀 목록 조회 (삭제된 팀 포함)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, creator_id, creator_name, created_at, is_active
        FROM teams 
        ORDER BY created_at DESC
    """)
    
    teams_data = cursor.fetchall()
    
    # 각 팀의 멤버 정보 가져오기
    teams = []
    for team in teams_data:
        team_dict = dict(team)
        cursor.execute("""
            SELECT user_name, position, joined_at
            FROM team_members 
            WHERE team_id = ? 
            ORDER BY joined_at
        """, (team['id'],))
        team_dict['members'] = cursor.fetchall()
        teams.append(team_dict)
    
    conn.close()
    
    return templates.TemplateResponse("teams.html", {
        "request": request,
        "teams": teams,
        "total_teams": len(teams)
    })

@app.get("/teams/add", response_class=HTMLResponse)
async def add_team_form(request: Request):
    """팀 등록 폼"""
    return templates.TemplateResponse("team_form.html", {
        "request": request,
        "team": None,
        "action": "add"
    })

@app.post("/teams/add", response_class=HTMLResponse)
async def add_team(request: Request, 
                   name: str = Form(...),
                   creator_name: str = Form(...)):
    """팀 등록"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO teams (name, creator_id, creator_name, created_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (name, f"temp_{datetime.now().timestamp()}", creator_name, datetime.now()))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/teams/edit/{team_id}", response_class=HTMLResponse)
async def edit_team_form(request: Request, team_id: int):
    """팀 수정 폼"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, creator_name
        FROM teams 
        WHERE id = ? AND is_active = 1
    """, (team_id,))
    
    team = cursor.fetchone()
    conn.close()
    
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다")
    
    return templates.TemplateResponse("team_form.html", {
        "request": request,
        "team": team,
        "action": "edit"
    })

@app.post("/teams/edit/{team_id}", response_class=HTMLResponse)
async def edit_team(request: Request, team_id: int,
                   name: str = Form(...),
                   creator_name: str = Form(...)):
    """팀 수정"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE teams 
            SET name = ?, creator_name = ?
            WHERE id = ? AND is_active = 1
        """, (name, creator_name, team_id))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/teams/delete/{team_id}", response_class=HTMLResponse)
async def delete_team(request: Request, team_id: int):
    """팀 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE teams 
            SET is_active = 0
            WHERE id = ?
        """, (team_id,))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/teams/restore/{team_id}", response_class=HTMLResponse)
async def restore_team(request: Request, team_id: int):
    """팀 복구 (삭제 취소)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE teams 
            SET is_active = 1
            WHERE id = ?
        """, (team_id,))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=302)
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/statistics", response_class=HTMLResponse)
async def view_statistics(request: Request):
    """통계 정보 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 전체 사용자 수
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_active = 1")
    total_users = cursor.fetchone()['count']
    
    # 포지션별 사용자 수
    cursor.execute("""
        SELECT position, COUNT(*) as count 
        FROM users 
        WHERE is_active = 1 AND position IS NOT NULL
        GROUP BY position
        ORDER BY count DESC
    """)
    position_stats = cursor.fetchall()
    
    # 전체 팀 수
    cursor.execute("SELECT COUNT(*) as count FROM teams WHERE is_active = 1")
    total_teams = cursor.fetchone()['count']
    
    # 팀별 멤버 수
    cursor.execute("""
        SELECT t.name, COUNT(tm.id) as member_count
        FROM teams t
        LEFT JOIN team_members tm ON t.id = tm.team_id
        WHERE t.is_active = 1
        GROUP BY t.id, t.name
        ORDER BY member_count DESC
    """)
    team_stats = cursor.fetchall()
    
    conn.close()
    
    return templates.TemplateResponse("statistics.html", {
        "request": request,
        "total_users": total_users,
        "position_stats": position_stats,
        "total_teams": total_teams,
        "team_stats": team_stats
    })

@app.get("/search", response_class=HTMLResponse)
async def search_users(request: Request, q: str = ""):
    """사용자 검색"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if q:
        cursor.execute("""
            SELECT user_id, name, school_major, position, insurance, email, created_at
            FROM users 
            WHERE is_active = 1 AND name LIKE ?
            ORDER BY name
        """, (f'%{q}%',))
        users = cursor.fetchall()
    else:
        users = []
    
    conn.close()
    
    return templates.TemplateResponse("search.html", {
        "request": request,
        "users": users,
        "query": q,
        "total_results": len(users)
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081) 