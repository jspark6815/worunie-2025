#!/usr/bin/env python3
"""
DB 조회 웹 인터페이스
"""

import sqlite3
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

app = FastAPI(title="DB Viewer")
templates = Jinja2Templates(directory="templates")



def get_slack_user_id_by_name(username: str) -> str:
    """Slack API를 통해 username으로 User ID를 가져옵니다"""
    if not SLACK_BOT_TOKEN:
        return None

    try:
        response = requests.get(
            "https://slack.com/api/users.list",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                users = data.get("members", [])
                for user in users:
                    if user.get("name") == username:
                        return user.get("id")

        return None

    except Exception as e:
        print(f"Error getting user ID for username {username}: {e}")
        return None

def get_member_display_name(user_name: str) -> tuple:
    """팀 멤버의 display_name을 가져옵니다"""
    # user_name이 Slack User ID 형식인지 확인 (U로 시작)
    if user_name.startswith('U'):
        # 이미 User ID인 경우
        user_id = user_name
        return user_id, user_name
    else:
        # username인 경우 User ID로 변환
        user_id = get_slack_user_id_by_name(user_name)
        if user_id:
            return user_id, user_name
        else:
            # User ID를 찾을 수 없는 경우
            return user_name, user_name

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect('/app/data/teams.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """홈페이지"""
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
    
    # 사용자 정보를 dict로 변환
    for user in users:
        user = dict(user)
        user['display_name'] = None
    
    conn.close()
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "total_users": len(users)
    })

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
        "user": dict(user),
        "action": "edit"
    })

@app.post("/users/edit/{user_id}")
async def edit_user(user_id: str, 
                   name: str = Form(...),
                   new_user_id: str = Form(...),  # 새로운 user_id (Slack ID)
                   school_major: str = Form(...),
                   position: str = Form(...),
                   insurance: str = Form(...),
                   email: str = Form(...)):
    """사용자 수정"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # user_id가 변경된 경우 중복 확인
        if new_user_id != user_id:
            cursor.execute("""
                SELECT name FROM users 
                WHERE user_id = ? AND is_active = 1
            """, (new_user_id,))
            
            if cursor.fetchone():
                conn.close()
                raise HTTPException(status_code=400, detail=f"Slack ID '{new_user_id}'는 이미 다른 사용자가 사용 중입니다.")
        
        # Slack ID 형식 검증 (U로 시작하는지 확인)
        if not new_user_id.startswith('U'):
            conn.close()
            raise HTTPException(status_code=400, detail="Slack ID는 'U'로 시작해야 합니다. (예: U099TRRAF4Y)")
        
        cursor.execute("""
            UPDATE users 
            SET user_id = ?, name = ?, school_major = ?, position = ?, insurance = ?, email = ?
            WHERE user_id = ? AND is_active = 1
        """, (new_user_id, name, school_major, position, insurance, email, user_id))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"사용자 수정 중 오류가 발생했습니다: {str(e)}")

@app.post("/users/quick-edit-slack-id/{user_id}")
async def quick_edit_slack_id(user_id: str, new_user_id: str = Form(...)):
    """빠른 Slack ID 변경"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Slack ID 형식 검증
        if not new_user_id.startswith('U'):
            conn.close()
            raise HTTPException(status_code=400, detail="Slack ID는 'U'로 시작해야 합니다.")
        
        # 중복 확인
        cursor.execute("""
            SELECT name FROM users 
            WHERE user_id = ? AND is_active = 1
        """, (new_user_id,))
        
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"Slack ID '{new_user_id}'는 이미 다른 사용자가 사용 중입니다.")
        
        # 기존 사용자 정보 가져오기
        cursor.execute("""
            SELECT name, school_major, position, insurance, email
            FROM users 
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        
        user = cursor.fetchone()
        if not user:
            conn.close()
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
        # Slack ID 업데이트
        cursor.execute("""
            UPDATE users 
            SET user_id = ?
            WHERE user_id = ? AND is_active = 1
        """, (new_user_id, user_id))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Slack ID 변경 중 오류가 발생했습니다: {str(e)}")

@app.post("/users/delete/{user_id}")
async def delete_user(user_id: str):
    """사용자 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE users 
            SET is_active = 0
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=303)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"사용자 삭제 중 오류가 발생했습니다: {str(e)}")

@app.get("/users/add", response_class=HTMLResponse)
async def add_user_form(request: Request):
    """사용자 등록 폼"""
    return templates.TemplateResponse("user_form.html", {
        "request": request,
        "user": None,
        "action": "add"
    })

@app.post("/users/add")
async def add_user(name: str = Form(...),
                  user_id: str = Form(...),
                  school_major: str = Form(...),
                  position: str = Form(...),
                  insurance: str = Form(...),
                  email: str = Form(...)):
    """사용자 등록"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Slack ID 형식 검증 (U로 시작하는지 확인)
        if not user_id.startswith('U'):
            conn.close()
            raise HTTPException(status_code=400, detail="Slack ID는 'U'로 시작해야 합니다. (예: U099TRRAF4Y)")
        
        # 중복 확인
        cursor.execute("""
            SELECT name FROM users 
            WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"Slack ID '{user_id}'는 이미 다른 사용자가 사용 중입니다.")
        
        cursor.execute("""
            INSERT INTO users (user_id, name, school_major, position, insurance, email, created_at, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (user_id, name, school_major, position, insurance, email, datetime.now()))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/users", status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"사용자 등록 중 오류가 발생했습니다: {str(e)}")

@app.get("/teams", response_class=HTMLResponse)
async def view_teams(request: Request):
    """팀 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, creator_id, creator_name, created_at, is_active
        FROM teams 
        WHERE is_active = 1 
        ORDER BY created_at DESC
    """)
    
    teams = cursor.fetchall()
    
    # 각 팀의 멤버 정보 가져오기
    for team in teams:
        # 팀 정보를 dict로 변환
        team = dict(team)
        team['creator_display_name'] = None
        
        cursor.execute("""
            SELECT user_name, position, joined_at
            FROM team_members 
            WHERE team_id = ? 
            ORDER BY joined_at
        """, (team['id'],))
        
        members = cursor.fetchall()
        
        # Slack API를 통해 실제 표시 이름 가져오기
        for member in members:
            user_name, display_name = get_member_display_name(member['user_name'])
            if display_name and display_name != user_name:
                member = dict(member)
                member['display_name'] = display_name
            else:
                member = dict(member)
                member['display_name'] = None
        
        team['members'] = members
    
    conn.close()
    
    return templates.TemplateResponse("teams.html", {
        "request": request,
        "teams": teams,
        "total_teams": len(teams)
    })

@app.get("/teams/edit/{team_id}", response_class=HTMLResponse)
async def edit_team_form(request: Request, team_id: int):
    """팀 수정 폼"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, name, creator_id, creator_name
        FROM teams 
        WHERE id = ? AND is_active = 1
    """, (team_id,))
    
    team = cursor.fetchone()
    conn.close()
    
    if not team:
        raise HTTPException(status_code=404, detail="팀을 찾을 수 없습니다")
    
    return templates.TemplateResponse("team_form.html", {
        "request": request,
        "team": dict(team),
        "is_edit": True
    })

@app.post("/teams/edit/{team_id}")
async def edit_team(team_id: int, name: str = Form(...)):
    """팀 수정"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE teams 
            SET name = ?
            WHERE id = ? AND is_active = 1
        """, (name, team_id))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=303)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"팀 수정 중 오류가 발생했습니다: {str(e)}")

@app.post("/teams/delete/{team_id}")
async def delete_team(team_id: int):
    """팀 삭제 (소프트 삭제)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE teams 
            SET is_active = 0
            WHERE id = ? AND is_active = 1
        """, (team_id,))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=303)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"팀 삭제 중 오류가 발생했습니다: {str(e)}")

@app.get("/teams/add", response_class=HTMLResponse)
async def add_team_form(request: Request):
    """팀 등록 폼"""
    return templates.TemplateResponse("team_form.html", {
        "request": request,
        "team": None,
        "is_edit": False
    })

@app.post("/teams/add")
async def add_team(name: str = Form(...),
                  creator_id: str = Form(...),
                  creator_name: str = Form(...)):
    """팀 등록"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO teams (name, creator_id, creator_name, created_at, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (name, creator_id, creator_name, datetime.now(), 1))
        
        conn.commit()
        conn.close()
        return RedirectResponse(url="/teams", status_code=303)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"팀 등록 중 오류가 발생했습니다: {str(e)}")

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
async def search_form(request: Request):
    """검색 폼"""
    return templates.TemplateResponse("search.html", {
        "request": request,
        "users": [],
        "teams": [],
        "query": "",
        "search_type": "users"
    })

@app.post("/search", response_class=HTMLResponse)
async def search_results(request: Request, 
                        query: str = Form(...),
                        search_type: str = Form(...)):
    """검색 결과"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    users = []
    teams = []
    
    if search_type == "users" or search_type == "all":
        # 사용자 검색
        cursor.execute("""
            SELECT user_id, name, school_major, position, insurance, email, created_at
            FROM users 
            WHERE is_active = 1 AND (
                name LIKE ? OR 
                school_major LIKE ? OR 
                position LIKE ? OR 
                email LIKE ?
            )
            ORDER BY name
        """, (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%'))
        
        users = cursor.fetchall()
        
        # 사용자 정보를 dict로 변환
        for user in users:
            user = dict(user)
            user['display_name'] = None
    
    if search_type == "teams" or search_type == "all":
        # 팀 검색
        cursor.execute("""
            SELECT id, name, creator_id, creator_name, created_at, is_active
            FROM teams 
            WHERE is_active = 1 AND (
                name LIKE ? OR 
                creator_name LIKE ?
            )
            ORDER BY created_at DESC
        """, (f'%{query}%', f'%{query}%'))
        
        teams = cursor.fetchall()
        
        # 각 팀의 멤버 정보 가져오기
        for team in teams:
            # 팀 정보를 dict로 변환
            team = dict(team)
            team['creator_display_name'] = None
            
            cursor.execute("""
                SELECT user_name, position, joined_at
                FROM team_members 
                WHERE team_id = ? 
                ORDER BY joined_at
            """, (team['id'],))
            
            members = cursor.fetchall()
            
            # Slack API를 통해 실제 표시 이름 가져오기
            for member in members:
                user_name, display_name = get_member_display_name(member['user_name'])
                if display_name and display_name != user_name:
                    member = dict(member)
                    member['display_name'] = display_name
                else:
                    member = dict(member)
                    member['display_name'] = None
            
            team['members'] = members
    
    conn.close()
    
    return templates.TemplateResponse("search.html", {
        "request": request,
        "users": users,
        "teams": teams,
        "query": query,
        "search_type": search_type
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081) 