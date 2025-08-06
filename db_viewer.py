#!/usr/bin/env python3
"""
DB 조회 웹 인터페이스
"""

import sqlite3
import os
from datetime import datetime

def get_db_connection():
    """데이터베이스 연결"""
    conn = sqlite3.connect('teams.db')
    conn.row_factory = sqlite3.Row
    return conn

def view_users():
    """사용자 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n👥 사용자 목록")
    print("=" * 80)
    
    cursor.execute("""
        SELECT user_id, name, school_major, position, insurance, email, created_at
        FROM users 
        WHERE is_active = 1 
        ORDER BY name
    """)
    
    users = cursor.fetchall()
    
    if not users:
        print("❌ 등록된 사용자가 없습니다.")
        return
    
    print(f"📊 총 {len(users)}명의 사용자")
    print()
    
    for user in users:
        print(f"👤 {user['name']}")
        print(f"   Slack ID: {user['user_id']}")
        print(f"   학교/전공: {user['school_major'] or '미입력'}")
        print(f"   포지션: {user['position'] or '미입력'}")
        print(f"   4대보험: {user['insurance'] or '미입력'}")
        print(f"   이메일: {user['email'] or '미입력'}")
        print(f"   등록일: {user['created_at']}")
        print("-" * 40)
    
    conn.close()

def view_teams():
    """팀 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n📋 팀 목록")
    print("=" * 80)
    
    cursor.execute("""
        SELECT id, name, creator_id, creator_name, created_at, is_active
        FROM teams 
        WHERE is_active = 1 
        ORDER BY created_at DESC
    """)
    
    teams = cursor.fetchall()
    
    if not teams:
        print("❌ 생성된 팀이 없습니다.")
        return
    
    print(f"📊 총 {len(teams)}개의 팀")
    print()
    
    for team in teams:
        print(f"🏆 {team['name']}")
        print(f"   팀장: {team['creator_name']} ({team['creator_id']})")
        print(f"   생성일: {team['created_at']}")
        
        # 팀 멤버 조회
        cursor.execute("""
            SELECT user_name, position, joined_at
            FROM team_members 
            WHERE team_id = ? 
            ORDER BY joined_at
        """, (team['id'],))
        
        members = cursor.fetchall()
        if members:
            print("   👥 팀 멤버:")
            for member in members:
                print(f"      • {member['user_name']} ({member['position']}) - {member['joined_at']}")
        else:
            print("   👥 팀 멤버: 없음")
        
        print("-" * 40)
    
    conn.close()

def view_team_members():
    """팀 멤버 상세 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n👥 팀 멤버 상세 정보")
    print("=" * 80)
    
    cursor.execute("""
        SELECT tm.id, tm.user_name, tm.position, tm.joined_at,
               t.name as team_name, t.creator_name
        FROM team_members tm
        JOIN teams t ON tm.team_id = t.id
        WHERE t.is_active = 1
        ORDER BY t.name, tm.joined_at
    """)
    
    members = cursor.fetchall()
    
    if not members:
        print("❌ 팀에 속한 멤버가 없습니다.")
        return
    
    print(f"📊 총 {len(members)}명의 팀 멤버")
    print()
    
    current_team = None
    for member in members:
        if current_team != member['team_name']:
            current_team = member['team_name']
            print(f"\n🏆 {current_team} (팀장: {member['creator_name']})")
            print("-" * 30)
        
        print(f"   • {member['user_name']} ({member['position']}) - {member['joined_at']}")
    
    conn.close()

def search_user(name=None):
    """사용자 검색"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if name:
        cursor.execute("""
            SELECT user_id, name, school_major, position, insurance, email, created_at
            FROM users 
            WHERE is_active = 1 AND name LIKE ?
            ORDER BY name
        """, (f'%{name}%',))
    else:
        name = input("검색할 사용자 이름을 입력하세요: ").strip()
        if not name:
            print("❌ 검색어를 입력해주세요.")
            conn.close()
            return
        
        cursor.execute("""
            SELECT user_id, name, school_major, position, insurance, email, created_at
            FROM users 
            WHERE is_active = 1 AND name LIKE ?
            ORDER BY name
        """, (f'%{name}%',))
    
    users = cursor.fetchall()
    
    if not users:
        print(f"❌ '{name}'과 일치하는 사용자를 찾을 수 없습니다.")
        conn.close()
        return
    
    print(f"\n🔍 '{name}' 검색 결과")
    print("=" * 80)
    print(f"📊 {len(users)}명의 사용자")
    print()
    
    for user in users:
        print(f"👤 {user['name']}")
        print(f"   Slack ID: {user['user_id']}")
        print(f"   학교/전공: {user['school_major'] or '미입력'}")
        print(f"   포지션: {user['position'] or '미입력'}")
        print(f"   4대보험: {user['insurance'] or '미입력'}")
        print(f"   이메일: {user['email'] or '미입력'}")
        print(f"   등록일: {user['created_at']}")
        print("-" * 40)
    
    conn.close()

def view_statistics():
    """통계 정보 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("\n📊 통계 정보")
    print("=" * 80)
    
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
    
    print(f"👥 전체 사용자: {total_users}명")
    print()
    
    print("📋 포지션별 분포:")
    for stat in position_stats:
        print(f"   • {stat['position']}: {stat['count']}명")
    print()
    
    print(f"🏆 전체 팀: {total_teams}개")
    print()
    
    print("📋 팀별 멤버 수:")
    for stat in team_stats:
        print(f"   • {stat['name']}: {stat['member_count']}명")
    
    conn.close()

def main():
    """메인 메뉴"""
    while True:
        print("\n" + "=" * 50)
        print("🗄️  DB 조회 도구")
        print("=" * 50)
        print("1. 사용자 목록 조회")
        print("2. 팀 목록 조회")
        print("3. 팀 멤버 상세 조회")
        print("4. 사용자 검색")
        print("5. 통계 정보")
        print("6. 종료")
        print("=" * 50)
        
        choice = input("\n선택하세요 (1-6): ").strip()
        
        if choice == "1":
            view_users()
        elif choice == "2":
            view_teams()
        elif choice == "3":
            view_team_members()
        elif choice == "4":
            search_user()
        elif choice == "5":
            view_statistics()
        elif choice == "6":
            print("👋 종료합니다.")
            break
        else:
            print("❌ 잘못된 선택입니다. 1-6 중에서 선택하세요.")
        
        input("\n계속하려면 Enter를 누르세요...")

if __name__ == "__main__":
    main() 