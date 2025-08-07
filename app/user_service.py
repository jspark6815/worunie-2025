from sqlalchemy.orm import Session
from .models import User, POSITIONS
import logging

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: Session):
        self.db = db
    
    def update_user_slack_id(self, name: str, slack_user_id: str) -> dict:
        """사용자 이름으로 찾아서 Slack User ID를 업데이트합니다"""
        try:
            # 이름으로 사용자 찾기
            user = self.db.query(User).filter(User.name == name, User.is_active == True).first()
            
            if not user:
                return {"success": False, "message": f"사용자 '{name}'를 찾을 수 없습니다."}
            
            # 이미 올바른 Slack User ID가 설정되어 있는지 확인
            if user.user_id == slack_user_id:
                return {"success": True, "message": f"사용자 '{name}'의 Slack ID가 이미 올바르게 설정되어 있습니다."}
            
            # Slack User ID 업데이트
            old_user_id = user.user_id
            user.user_id = slack_user_id
            
            self.db.commit()
            
            logger.info(f"User '{name}' Slack ID updated: {old_user_id} -> {slack_user_id}")
            return {"success": True, "message": f"사용자 '{name}'의 Slack ID가 업데이트되었습니다."}
            
        except Exception as e:
            logger.error(f"Error updating user Slack ID: {e}")
            self.db.rollback()
            return {"success": False, "message": "사용자 ID 업데이트 중 오류가 발생했습니다."}
    
    def get_user_info(self, user_id: str) -> dict:
        """Slack User ID로 사용자 정보 조회"""
        try:
            user = self.db.query(User).filter(User.user_id == user_id, User.is_active == True).first()
            if not user:
                return {"success": False, "message": f"사용자 ID '{user_id}'를 찾을 수 없습니다."}
            
            return {
                "success": True,
                "user": {
                    "user_id": user.user_id,
                    "name": user.name,
                    "school_major": user.school_major,
                    "position": user.position,
                    "insurance": user.insurance,
                    "email": user.email,
                    "created_at": user.created_at.strftime("%Y-%m-%d %H:%M")
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return {"success": False, "message": "사용자 정보 조회 중 오류가 발생했습니다."}
    
    def get_user_by_name(self, name: str) -> dict:
        """사용자 이름으로 사용자 정보 조회 (Slack ID 기준)"""
        try:
            user = self.db.query(User).filter(User.name == name, User.is_active == True).first()
            if not user:
                return {"success": False, "message": f"사용자 '{name}'를 찾을 수 없습니다."}
            
            return {
                "success": True,
                "user": {
                    "user_id": user.user_id,
                    "name": user.name,
                    "school_major": user.school_major,
                    "position": user.position,
                    "insurance": user.insurance,
                    "email": user.email,
                    "created_at": user.created_at.strftime("%Y-%m-%d %H:%M")
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user by name: {e}")
            return {"success": False, "message": "사용자 정보 조회 중 오류가 발생했습니다."}
    
    def get_all_users(self) -> dict:
        """모든 사용자 목록 조회"""
        try:
            users = self.db.query(User).filter(User.is_active == True).all()
            
            user_list = []
            for user in users:
                user_list.append({
                    "user_id": user.user_id,
                    "name": user.name,
                    "school_major": user.school_major,
                    "position": user.position,
                    "insurance": user.insurance,
                    "email": user.email,
                    "created_at": user.created_at.strftime("%Y-%m-%d %H:%M")
                })
            
            return {"success": True, "users": user_list}
            
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return {"success": False, "message": "사용자 목록 조회 중 오류가 발생했습니다."}
    
    def create_user(self, name: str, slack_user_id: str, school_major: str = None, 
                   position: str = None, insurance: str = None, email: str = None) -> dict:
        """새로운 사용자 생성"""
        try:
            # 중복 확인 (Slack User ID 기준)
            existing_user = self.db.query(User).filter(User.user_id == slack_user_id, User.is_active == True).first()
            if existing_user:
                return {"success": False, "message": f"Slack User ID '{slack_user_id}'로 등록된 사용자가 이미 존재합니다."}
            
            # 이름 중복 확인
            existing_name = self.db.query(User).filter(User.name == name, User.is_active == True).first()
            if existing_name:
                return {"success": False, "message": f"이름 '{name}'으로 등록된 사용자가 이미 존재합니다."}
            
            new_user = User(
                user_id=slack_user_id,
                name=name,
                school_major=school_major,
                position=position,
                insurance=insurance,
                email=email
            )
            
            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)
            
            logger.info(f"User '{name}' created with Slack ID: {slack_user_id}")
            return {"success": True, "message": f"사용자 '{name}'이(가) 생성되었습니다."}
            
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            self.db.rollback()
            return {"success": False, "message": "사용자 생성 중 오류가 발생했습니다."}
    
    def update_user(self, slack_user_id: str, **kwargs) -> dict:
        """사용자 정보 업데이트 (Slack User ID 기준)"""
        try:
            user = self.db.query(User).filter(User.user_id == slack_user_id, User.is_active == True).first()
            if not user:
                return {"success": False, "message": f"Slack User ID '{slack_user_id}'를 찾을 수 없습니다."}
            
            # 업데이트할 필드들
            if 'name' in kwargs:
                user.name = kwargs['name']
            if 'school_major' in kwargs:
                user.school_major = kwargs['school_major']
            if 'position' in kwargs:
                user.position = kwargs['position']
            if 'insurance' in kwargs:
                user.insurance = kwargs['insurance']
            if 'email' in kwargs:
                user.email = kwargs['email']
            
            self.db.commit()
            
            logger.info(f"User '{user.name}' updated")
            return {"success": True, "message": f"사용자 '{user.name}'의 정보가 업데이트되었습니다."}
            
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            self.db.rollback()
            return {"success": False, "message": "사용자 정보 업데이트 중 오류가 발생했습니다."}
    
    def delete_user(self, slack_user_id: str) -> dict:
        """사용자 삭제 (실제 삭제 대신 비활성화)"""
        try:
            user = self.db.query(User).filter(User.user_id == slack_user_id, User.is_active == True).first()
            if not user:
                return {"success": False, "message": f"Slack User ID '{slack_user_id}'를 찾을 수 없습니다."}
            
            user.is_active = False
            self.db.commit()
            
            logger.info(f"User '{user.name}' deactivated")
            return {"success": True, "message": f"사용자 '{user.name}'이(가) 삭제되었습니다."}
            
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            self.db.rollback()
            return {"success": False, "message": "사용자 삭제 중 오류가 발생했습니다."}
    
 