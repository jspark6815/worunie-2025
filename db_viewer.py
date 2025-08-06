#!/usr/bin/env python3
"""
DB 조회 웹 인터페이스
"""

import sqlite3
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

app = FastAPI(title="DB Viewer")
templates = Jinja2Templates(directory="templates")

def get_slack_user_display_name(user_id: str) -> str:
    """Slack API를 통해 User ID로 실제 표시 이름을 가져옵니다"""
    if not SLACK_BOT_TOKEN:
        return None

    try:
        response = requests.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"user": user_id}
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                user = data.get("user", {})
                # real_name을 우선적으로 사용, 없으면 display_name 사용
                display_name = user.get("real_name") or user.get("display_name") or user.get("name")
                return display_name

        return None

    except Exception as e:
        print(f"Error getting display name for user ID {user_id}: {e}")
        return None

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect('teams.db')
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
    
    # Slack API를 통해 실제 표시 이름 가져오기
    for user in users:
        display_name = get_slack_user_display_name(user['user_id'])
        if display_name and display_name != user['name']:
            user = dict(user)
            user['display_name'] = display_name
        else:
            user = dict(user)
            user['display_name'] = None
    
    conn.close()
    
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users
    })

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
        cursor.execute("""
            SELECT user_name, position, joined_at
            FROM team_members 
            WHERE team_id = ? 
            ORDER BY joined_at
        """, (team['id'],))
        
        members = cursor.fetchall()
        
        # Slack API를 통해 실제 표시 이름 가져오기
        for member in members:
            display_name = get_slack_user_display_name(member['user_name'])
            if display_name and display_name != member['user_name']:
                member = dict(member)
                member['display_name'] = display_name
            else:
                member = dict(member)
                member['display_name'] = None
        
        team = dict(team)
        team['members'] = members
    
    conn.close()
    
    return templates.TemplateResponse("teams.html", {
        "request": request,
        "teams": teams
    })

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081) 