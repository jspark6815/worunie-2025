from sqlalchemy.orm import Session
from .models import Team, TeamMember, TEAM_COMPOSITION
import logging

logger = logging.getLogger(__name__)

class TeamBuildingService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_team(self, team_name: str, creator_id: str, creator_name: str) -> dict:
        """팀 생성"""
        try:
            # 팀명 중복 확인
            existing_team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if existing_team:
                return {"success": False, "message": f"팀명 '{team_name}'이 이미 존재합니다."}
            
            # 새 팀 생성
            new_team = Team(
                name=team_name,
                creator_id=creator_id,
                creator_name=creator_name
            )
            self.db.add(new_team)
            self.db.commit()
            self.db.refresh(new_team)
            
            logger.info(f"Team '{team_name}' created by {creator_name}")
            return {"success": True, "message": f"팀 '{team_name}'이 생성되었습니다!", "team_id": new_team.id}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating team: {e}")
            return {"success": False, "message": "팀 생성 중 오류가 발생했습니다."}
    
    def delete_team(self, team_name: str, user_id: str) -> dict:
        """팀 삭제 (팀장만 가능)"""
        try:
            # 팀 찾기
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다."}
            
            # 팀장 권한 확인
            if team.creator_id != user_id:
                return {"success": False, "message": f"팀을 삭제할 권한이 없습니다. 팀장만 삭제할 수 있습니다."}
            
            # 팀 멤버들 삭제
            members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
            for member in members:
                self.db.delete(member)
            
            # 팀 비활성화 (실제 삭제 대신 is_active = False)
            team.is_active = False
            self.db.commit()
            
            logger.info(f"Team '{team_name}' deleted by {user_id}")
            return {"success": True, "message": f"팀 '{team_name}'이 삭제되었습니다."}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting team: {e}")
            return {"success": False, "message": "팀 삭제 중 오류가 발생했습니다."}
    
    def add_member_to_team(self, team_name: str, position: str, user_id: str, user_name: str) -> dict:
        """팀에 멤버 추가"""
        try:
            # 팀 찾기
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다."}
            
            # 포지션 유효성 검사
            if position not in TEAM_COMPOSITION:
                return {"success": False, "message": f"유효하지 않은 포지션입니다. 가능한 포지션: {', '.join(TEAM_COMPOSITION.keys())}"}
            
            # 이미 해당 포지션에 멤버가 있는지 확인
            existing_member = self.db.query(TeamMember).filter(
                TeamMember.team_id == team.id,
                TeamMember.position == position
            ).first()
            
            if existing_member:
                return {"success": False, "message": f"'{position}' 포지션은 이미 채워져 있습니다."}
            
            # 사용자가 이미 다른 팀에 있는지 확인
            existing_user = self.db.query(TeamMember).filter(TeamMember.user_id == user_id).first()
            if existing_user:
                return {"success": False, "message": f"<@{user_id}>님은 이미 다른 팀에 속해 있습니다."}
            
            # 멤버 추가
            new_member = TeamMember(
                team_id=team.id,
                user_id=user_id,
                user_name=user_name,
                position=position
            )
            self.db.add(new_member)
            self.db.commit()
            
            logger.info(f"Member {user_name} added to team {team_name} as {position}")
            return {"success": True, "message": f"<@{user_id}>님이 '{team_name}' 팀의 {position}으로 추가되었습니다!"}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding member to team: {e}")
            return {"success": False, "message": "멤버 추가 중 오류가 발생했습니다."}
    
    def remove_member_from_team(self, team_name: str, target_user_id: str, user_id: str) -> dict:
        """팀에서 멤버 삭제 (팀장만 가능)"""
        try:
            # 팀 찾기
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다."}
            
            # 팀장 권한 확인
            if team.creator_id != user_id:
                return {"success": False, "message": f"팀원을 삭제할 권한이 없습니다. 팀장만 삭제할 수 있습니다."}
            
            # 삭제할 멤버 찾기
            member = self.db.query(TeamMember).filter(
                TeamMember.team_id == team.id,
                TeamMember.user_id == target_user_id
            ).first()
            
            if not member:
                return {"success": False, "message": f"<@{target_user_id}>님은 '{team_name}' 팀의 멤버가 아닙니다."}
            
            # 팀장 자신을 삭제하려고 하는지 확인
            if target_user_id == user_id:
                return {"success": False, "message": "팀장은 자신을 삭제할 수 없습니다. 팀을 삭제하려면 `/팀삭제` 명령어를 사용하세요."}
            
            # 팀에 최소 1명은 남아있어야 함 (팀장 제외)
            total_members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).count()
            if total_members <= 1:
                return {"success": False, "message": "팀에 최소 1명의 멤버는 남아있어야 합니다."}
            
            # 멤버 삭제
            self.db.delete(member)
            self.db.commit()
            
            logger.info(f"Member {target_user_id} removed from team {team_name} by {user_id}")
            return {"success": True, "message": f"<@{target_user_id}>님이 '{team_name}' 팀에서 삭제되었습니다!"}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error removing member from team: {e}")
            return {"success": False, "message": "팀원 삭제 중 오류가 발생했습니다."}
    
    def get_team_info(self, team_name: str) -> dict:
        """팀 정보 조회"""
        try:
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다."}
            
            members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
            
            # 팀 구성 상태 확인
            team_status = {}
            for position, required_count in TEAM_COMPOSITION.items():
                current_count = len([m for m in members if m.position == position])
                team_status[position] = {
                    "required": required_count,
                    "current": current_count,
                    "filled": current_count >= required_count
                }
            
            # 멤버 목록
            member_list = []
            for member in members:
                member_list.append(f"• {member.position}: <@{member.user_id}> ({member.user_name})")
            
            return {
                "success": True,
                "team_name": team_name,
                "members": member_list,
                "status": team_status,
                "created_at": team.created_at.strftime("%Y-%m-%d %H:%M"),
                "creator_name": team.creator_name,
                "creator_id": team.creator_id
            }
            
        except Exception as e:
            logger.error(f"Error getting team info: {e}")
            return {"success": False, "message": "팀 정보 조회 중 오류가 발생했습니다."}
    
    def get_all_teams(self) -> dict:
        """모든 팀 목록 조회"""
        try:
            teams = self.db.query(Team).filter(Team.is_active == True).all()
            
            team_list = []
            for team in teams:
                members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
                member_count = len(members)
                total_required = sum(TEAM_COMPOSITION.values())
                
                team_list.append({
                    "name": team.name,
                    "member_count": member_count,
                    "total_required": total_required,
                    "is_complete": member_count >= total_required,
                    "created_at": team.created_at.strftime("%Y-%m-%d %H:%M")
                })
            
            return {"success": True, "teams": team_list}
            
        except Exception as e:
            logger.error(f"Error getting all teams: {e}")
            return {"success": False, "message": "팀 목록 조회 중 오류가 발생했습니다."} 