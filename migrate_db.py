#!/usr/bin/env python3
"""
데이터베이스 마이그레이션 스크립트
기존 팀 데이터에 팀장 정보를 추가합니다.
"""

import sqlite3
import os

def migrate_database():
    """데이터베이스 마이그레이션 실행"""
    db_path = "teams.db"
    
    if not os.path.exists(db_path):
        print("데이터베이스 파일이 없습니다. 새로 생성됩니다.")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 기존 테이블에 creator_id, creator_name 컬럼이 있는지 확인
        cursor.execute("PRAGMA table_info(teams)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'creator_id' not in columns:
            print("팀장 정보 컬럼을 추가합니다...")
            cursor.execute("ALTER TABLE teams ADD COLUMN creator_id TEXT")
            cursor.execute("ALTER TABLE teams ADD COLUMN creator_name TEXT")
            print("✅ 팀장 정보 컬럼이 추가되었습니다.")
        else:
            print("팀장 정보 컬럼이 이미 존재합니다.")
        
        # 기존 팀 데이터에 기본 팀장 정보 설정 (필요한 경우)
        cursor.execute("SELECT id, name FROM teams WHERE creator_id IS NULL")
        teams_without_creator = cursor.fetchall()
        
        if teams_without_creator:
            print(f"기존 팀 {len(teams_without_creator)}개에 기본 팀장 정보를 설정합니다...")
            for team_id, team_name in teams_without_creator:
                cursor.execute(
                    "UPDATE teams SET creator_id = ?, creator_name = ? WHERE id = ?",
                    (f"unknown_{team_id}", f"팀장_{team_name}", team_id)
                )
            print("✅ 기본 팀장 정보가 설정되었습니다.")
        
        conn.commit()
        print("마이그레이션이 완료되었습니다!")
        
    except Exception as e:
        print(f"마이그레이션 중 오류 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database() 