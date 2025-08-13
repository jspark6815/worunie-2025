from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# 데이터베이스 설정
DATABASE_URL = "sqlite:////app/data/teams.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, index=True)  # Slack user ID
    name = Column(String, nullable=False)
    school_major = Column(String)  # 학교/전공
    position = Column(String)  # 프론트엔드, 백엔드, 기획, 디자인
    insurance = Column(String)  # Y/N
    email = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    creator_id = Column(String, index=True)  # 팀장의 Slack user ID
    creator_name = Column(String)  # 팀장의 이름
    
    # 팀 멤버 관계
    members = relationship("TeamMember", back_populates="team")

class TeamMember(Base):
    __tablename__ = "team_members"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"))
    user_id = Column(String, index=True)  # Slack user ID
    user_name = Column(String)  # Slack user name
    position = Column(String)  # BE, FE, Designer, Planner
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    # 팀 관계
    team = relationship("Team", back_populates="members")

# 데이터베이스 테이블 생성 (기존 테이블이 있으면 유지)
# Base.metadata.create_all(bind=engine)  # 테이블이 없으면 생성

# 포지션 정의
POSITIONS = ["프론트엔드", "백엔드", "기획", "디자인"]


# 팀 제한 설정
MAX_TEAMS_5 = 9  # 5인팀 최대 9팀
MAX_TEAMS_4 = 3   # 4인팀 최대 3팀

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 