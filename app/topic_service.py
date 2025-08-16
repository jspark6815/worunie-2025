from sqlalchemy.orm import Session
from .models import TopicSelection, Team, TOPICS, MAX_TEAMS_PER_TOPIC
from datetime import datetime, time
import pytz

class TopicSelectionService:
    def __init__(self, db: Session):
        self.db = db
    
    def is_selection_time(self) -> bool:
        """주제선정 시간인지 확인 (한국 시간 15:30 이후)"""
        korea_tz = pytz.timezone('Asia/Seoul')
        now = datetime.now(korea_tz)
        start_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return now >= start_time
    
    def get_topic_selection(self, team_name: str) -> dict:
        """팀의 주제선정 정보 조회"""
        try:
            selection = self.db.query(TopicSelection).filter(
                TopicSelection.team_name == team_name,
                TopicSelection.is_active == True
            ).first()
            
            if selection:
                return {
                    "success": True,
                    "topic": selection.topic,
                    "created_at": selection.created_at,
                    "updated_at": selection.updated_at,
                    "creator_name": selection.creator_name
                }
            else:
                return {
                    "success": False,
                    "message": "주제선정 정보가 없습니다."
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"주제선정 정보 조회 중 오류가 발생했습니다: {str(e)}"
            }
    
    def get_topic_counts(self) -> dict:
        """각 주제별 선택된 팀 수 조회"""
        try:
            work_count = self.db.query(TopicSelection).filter(
                TopicSelection.topic == "WORK",
                TopicSelection.is_active == True
            ).count()
            
            run_count = self.db.query(TopicSelection).filter(
                TopicSelection.topic == "RUN",
                TopicSelection.is_active == True
            ).count()
            
            return {
                "success": True,
                "work_count": work_count,
                "run_count": run_count,
                "work_available": work_count < MAX_TEAMS_PER_TOPIC,
                "run_available": run_count < MAX_TEAMS_PER_TOPIC
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"주제별 팀 수 조회 중 오류가 발생했습니다: {str(e)}"
            }
    
    def select_topic(self, team_name: str, topic: str, creator_id: str, creator_name: str) -> dict:
        """주제선정"""
        try:
            # 시간 확인
            if not self.is_selection_time():
                return {
                    "success": False,
                    "message": "주제선정은 한국 시간 15:30 이후에만 가능합니다."
                }
            
            # 주제 유효성 확인
            topic_upper = topic.upper()
            if topic_upper not in TOPICS:
                return {
                    "success": False,
                    "message": f"유효하지 않은 주제입니다. 'WORK' 또는 'RUN' 중 선택해주세요."
                }
            
            # 팀 존재 확인
            team = self.db.query(Team).filter(
                Team.name == team_name,
                Team.is_active == True
            ).first()
            
            if not team:
                return {
                    "success": False,
                    "message": f"팀 '{team_name}'을(를) 찾을 수 없습니다."
                }
            
            # 팀장 권한 확인
            if team.creator_id != creator_id:
                return {
                    "success": False,
                    "message": "팀장만 주제를 선택할 수 있습니다."
                }
            
            # 기존 주제선정 확인
            existing_selection = self.db.query(TopicSelection).filter(
                TopicSelection.team_name == team_name,
                TopicSelection.is_active == True
            ).first()
            
            # 주제별 팀 수 확인
            topic_counts = self.get_topic_counts()
            if not topic_counts["success"]:
                return topic_counts
            
            if topic_upper == "WORK":
                if topic_counts["work_count"] >= MAX_TEAMS_PER_TOPIC:
                    return {
                        "success": False,
                        "message": f"WORK 주제는 이미 최대 {MAX_TEAMS_PER_TOPIC}팀이 선택했습니다."
                    }
            else:  # RUN
                if topic_counts["run_count"] >= MAX_TEAMS_PER_TOPIC:
                    return {
                        "success": False,
                        "message": f"RUN 주제는 이미 최대 {MAX_TEAMS_PER_TOPIC}팀이 선택했습니다."
                    }
            
            # 기존 선택이 있으면 업데이트, 없으면 새로 생성
            if existing_selection:
                # 기존 선택과 다른 주제인 경우에만 업데이트
                if existing_selection.topic != topic_upper:
                    old_topic = existing_selection.topic
                    existing_selection.topic = topic_upper
                    existing_selection.updated_at = datetime.utcnow()
                    self.db.commit()
                    
                    return {
                        "success": True,
                        "message": f"주제가 '{old_topic}'에서 '{topic_upper}'로 변경되었습니다."
                    }
                else:
                    return {
                        "success": False,
                        "message": f"이미 '{topic_upper}' 주제를 선택했습니다."
                    }
            else:
                # 새로운 주제선정 생성
                new_selection = TopicSelection(
                    team_id=team.id,
                    team_name=team_name,
                    topic=topic_upper,
                    creator_id=creator_id,
                    creator_name=creator_name
                )
                
                self.db.add(new_selection)
                self.db.commit()
                
                return {
                    "success": True,
                    "message": f"'{topic_upper}' 주제를 선택했습니다."
                }
                
        except Exception as e:
            self.db.rollback()
            return {
                "success": False,
                "message": f"주제선정 중 오류가 발생했습니다: {str(e)}"
            }
    
    def get_all_topic_selections(self) -> dict:
        """모든 주제선정 정보 조회"""
        try:
            selections = self.db.query(TopicSelection).filter(
                TopicSelection.is_active == True
            ).order_by(TopicSelection.created_at).all()
            
            result = []
            for selection in selections:
                result.append({
                    "team_name": selection.team_name,
                    "topic": selection.topic,
                    "creator_name": selection.creator_name,
                    "created_at": selection.created_at,
                    "updated_at": selection.updated_at
                })
            
            return {
                "success": True,
                "selections": result
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"주제선정 목록 조회 중 오류가 발생했습니다: {str(e)}"
            } 