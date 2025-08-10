from sqlalchemy.orm import Session
from .models import Team, TeamMember, TEAM_COMPOSITION, TEAM_COMPOSITION_5, TEAM_COMPOSITION_4, MAX_TEAMS_5, MAX_TEAMS_4
import logging
import requests
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")



class TeamBuildingService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_team(self, team_name: str, creator_id: str, creator_name: str) -> dict:
        """팀 생성"""
        try:
            # 팀명 중복 확인 (활성화된 팀만)
            existing_team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if existing_team:
                return {"success": False, "message": f"팀명 '{team_name}'이 이미 존재합니다."}
            
            # 비활성화된 팀이 있는지 확인하고 재활성화
            inactive_team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == False).first()
            if inactive_team:
                # 비활성화된 팀을 재활성화하고 팀장 정보 업데이트
                inactive_team.is_active = True
                inactive_team.creator_id = creator_id
                inactive_team.creator_name = creator_name
                inactive_team.created_at = datetime.utcnow()
                self.db.commit()
                
                logger.info(f"Team '{team_name}' reactivated by {creator_name}")
                return {"success": True, "message": f"팀 '{team_name}'이 재활성화되었습니다!", "team_id": inactive_team.id}
            
            # 팀 제한 확인 (전체 팀 수 제한)
            active_teams = self.db.query(Team).filter(Team.is_active == True).all()
            total_teams = len(active_teams)
            max_total_teams = MAX_TEAMS_5 + MAX_TEAMS_4  # 총 12팀
            
            if total_teams >= max_total_teams:
                return {"success": False, "message": f"팀은 최대 {max_total_teams}팀까지만 생성할 수 있습니다. (현재 {total_teams}팀)"}
            
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
    
    def delete_team(self, team_name: str, user_id: str, is_staff: bool = False) -> dict:
        """팀 삭제 (팀장 또는 staff만 가능)"""
        try:
            # 팀 찾기
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다."}
            
            # 팀장 또는 staff 권한 확인
            if team.creator_id != user_id and not is_staff:
                return {"success": False, "message": f"팀을 삭제할 권한이 없습니다. 팀장 또는 관리자만 삭제할 수 있습니다."}
            
            # 팀 멤버들 삭제
            members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
            for member in members:
                self.db.delete(member)
            
            # 팀 비활성화 (실제 삭제 대신 is_active = False)
            team.is_active = False
            self.db.commit()
            
            logger.info(f"Team '{team_name}' deleted by {user_id} (staff: {is_staff})")
            return {"success": True, "message": f"팀 '{team_name}'이 삭제되었습니다."}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting team: {e}")
            return {"success": False, "message": "팀 삭제 중 오류가 발생했습니다."}
    
    def add_member_to_team(self, team_name: str, user_id: str, user_name: str) -> dict:
        """팀에 멤버 추가 (사용자의 DB 포지션 자동 사용)"""
        try:
            logger.info(f"=== add_member_to_team called ===")
            logger.info(f"team_name: '{team_name}'")
            logger.info(f"user_id: '{user_id}'")
            logger.info(f"user_name: '{user_name}'")
            
            # 팀 찾기
            logger.info(f"Searching for team with name: '{team_name}'")
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            
            if not team:
                logger.error(f"Team '{team_name}' not found or not active")
                
                # 비슷한 이름의 팀이 있는지 확인
                similar_teams = self.db.query(Team).filter(
                    Team.name.like(f"%{team_name}%"),
                    Team.is_active == True
                ).all()
                
                if similar_teams:
                    team_names = [t.name for t in similar_teams]
                    return {
                        "success": False, 
                        "message": f"팀 '{team_name}'을 찾을 수 없습니다.\n\n비슷한 이름의 팀: {', '.join(team_names)}\n\n정확한 팀명을 입력해주세요."
                    }
                
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다.\n팀명을 확인하거나 먼저 팀을 생성해주세요."}
            
            logger.info(f"Found team: id={team.id}, name='{team.name}', creator_id='{team.creator_id}'")
            
            # 팀 객체 유효성 확인
            if not team or not hasattr(team, 'name') or not team.name:
                logger.error(f"Invalid team object: {team}")
                return {"success": False, "message": "팀 정보가 올바르지 않습니다. 다시 시도해주세요."}
            
            # 사용자의 DB 포지션 가져오기 (Slack User ID 기준)
            from .user_service import UserService
            user_service = UserService(self.db)
            user_result = user_service.get_user_info(user_id)
            
            if not user_result["success"]:
                logger.warning(f"User {user_id} not found in database")
                return {"success": False, "message": f"<@{user_id}>님은 데이터베이스에 등록되어 있지 않습니다.\n웹 DB 뷰어에서 사용자를 등록해주세요."}
            
            user_data = user_result["user"]
            db_position = user_data.get("position")
            logger.info(f"User {user_id} position from DB: '{db_position}'")
            
            if not db_position:
                logger.warning(f"User {user_id} has no position in database")
                return {"success": False, "message": f"<@{user_id}>님의 포지션이 데이터베이스에 등록되어 있지 않습니다.\n웹 DB 뷰어에서 포지션을 설정해주세요."}
            
            # DB 포지션을 팀 구성 규칙에 맞게 매핑
            position_mapping = {
                "백엔드": "BE",
                "프론트엔드": "FE", 
                "디자인": "Designer",
                "기획": "Planner"
            }
            
            position = position_mapping.get(db_position)
            if not position:
                logger.warning(f"User {user_id} position '{db_position}' not in mapping")
                return {"success": False, "message": f"<@{user_id}>님의 포지션 '{db_position}'은 팀 구성 규칙에 맞지 않습니다.\n가능한 포지션: 백엔드, 프론트엔드, 디자인, 기획"}
            
            logger.info(f"Mapped position: '{db_position}' -> '{position}'")
            
            # 사용자가 이미 팀에 속해있는지 확인 (Slack User ID 기준)
            existing_member = self.db.query(TeamMember).filter(TeamMember.user_id == user_id).first()
            if existing_member:
                existing_team = self.db.query(Team).filter(Team.id == existing_member.team_id).first()
                logger.warning(f"User {user_id} already in team '{existing_team.name if existing_team else 'Unknown'}'")
                return {"success": False, "message": f"<@{user_id}>님은 이미 '{existing_team.name if existing_team else 'Unknown'}' 팀에 속해 있습니다."}
            
            # 팀 제한 확인 (팀원 추가 시)
            current_members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
            current_member_count = len(current_members)
            logger.info(f"Current team member count: {current_member_count}")
            
            # 팀 인원수 제한 확인 (5인팀 또는 4인팀)
            if current_member_count >= 5:
                logger.warning(f"Team '{team_name}' already has maximum members (5)")
                return {"success": False, "message": "팀은 최대 5명까지만 구성할 수 있습니다."}
            
            # 4인팀 제한 확인
            if current_member_count >= 4:
                active_teams = self.db.query(Team).filter(Team.is_active == True).all()
                team_count_4 = 0
                
                for active_team in active_teams:
                    if active_team.id != team.id:  # 현재 팀 제외
                        member_count = self.db.query(TeamMember).filter(TeamMember.team_id == active_team.id).count()
                        if member_count >= 4:
                            team_count_4 += 1
                
                if team_count_4 >= MAX_TEAMS_4:
                    logger.warning(f"Maximum 4-person teams reached: {team_count_4}")
                    return {"success": False, "message": f"4인팀은 최대 {MAX_TEAMS_4}팀까지만 생성할 수 있습니다. (현재 {team_count_4}팀)"}
            
            # 멤버 추가
            logger.info(f"Adding member {user_name} to team {team.name} as {position}")
            new_member = TeamMember(
                team_id=team.id,
                user_id=user_id,
                user_name=user_name,
                position=position
            )
            self.db.add(new_member)
            self.db.commit()
            
            logger.info(f"Member {user_name} added to team {team.name} as {position}")
            return {"success": True, "message": f"<@{user_id}>님이 '{team.name}' 팀의 {position}으로 추가되었습니다!"}
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error adding member to team: {e}")
            return {"success": False, "message": "멤버 추가 중 오류가 발생했습니다."}
    
    def remove_member_from_team(self, team_name: str, target_user_id: str, user_id: str, is_staff: bool = False) -> dict:
        """팀에서 멤버 삭제 (팀장 또는 staff만 가능)"""
        try:
            # 팀 찾기
            team = self.db.query(Team).filter(Team.name == team_name, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": f"팀 '{team_name}'을 찾을 수 없습니다."}
            
            # 팀장 또는 staff 권한 확인
            if team.creator_id != user_id and not is_staff:
                return {"success": False, "message": f"팀원을 삭제할 권한이 없습니다. 팀장 또는 관리자만 삭제할 수 있습니다."}
            
            # 삭제할 멤버 찾기 (Slack User ID 기준)
            member = self.db.query(TeamMember).filter(
                TeamMember.team_id == team.id,
                TeamMember.user_id == target_user_id
            ).first()
            
            if not member:
                return {"success": False, "message": f"<@{target_user_id}>님은 '{team_name}' 팀의 멤버가 아닙니다."}
            
            # 팀장 자신을 삭제하려고 하는지 확인 (staff는 예외)
            if target_user_id == user_id and not is_staff:
                return {"success": False, "message": "팀장은 자신을 삭제할 수 없습니다. 팀을 삭제하려면 `/팀삭제` 명령어를 사용하세요."}
            
            # 팀에 최소 1명은 남아있어야 함 (팀장 제외, staff는 예외)
            if not is_staff:
                total_members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).count()
                if total_members <= 1:
                    return {"success": False, "message": "팀에 최소 1명의 멤버는 남아있어야 합니다."}
            
            # 멤버 삭제
            self.db.delete(member)
            self.db.commit()
            
            logger.info(f"Member {target_user_id} removed from team {team_name} by {user_id} (staff: {is_staff})")
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
            
            # 팀장을 팀원에 포함시키기 위해 팀장 정보도 추가
            creator_name = team.creator_name
            
            # 포지션별 현재 인원수 계산 (팀장 포함)
            position_counts = {}
            for member in members:
                position = member.position
                if position not in position_counts:
                    position_counts[position] = 0
                position_counts[position] += 1
            
            # 팀장의 포지션을 확인하고 카운트에 추가
            # 팀장의 포지션은 DB에서 가져오거나 기본값 사용
            from .user_service import UserService
            user_service = UserService(self.db)
            creator_info = user_service.get_user_info(team.creator_id)
            
            if creator_info["success"]:
                creator_position = creator_info["user"].get("position", "")
                # DB 포지션을 팀 구성 규칙에 맞게 매핑
                position_mapping = {
                    "백엔드": "BE",
                    "프론트엔드": "FE", 
                    "디자인": "Designer",
                    "기획": "Planner"
                }
                mapped_position = position_mapping.get(creator_position, creator_position)
                if mapped_position in position_counts:
                    position_counts[mapped_position] += 1
                else:
                    position_counts[mapped_position] = 1
            
            # 팀 유형 결정 (포지션 제한 없이 인원수만으로 판단)
            total_members = len(members) + 1  # 팀장 포함
            if total_members >= 5:
                team_type = "5인팀"
                required_composition = {"최대 인원": 5}
            elif total_members >= 4:
                team_type = "4인팀"
                required_composition = {"최대 인원": 4}
            else:
                team_type = "구성중"
                required_composition = {"최대 인원": 5}  # 기본값
            
            # 멤버 목록 (팀장 포함)
            member_list = []
            
            # 팀장을 먼저 추가
            member_list.append(f"• 팀장: {creator_name} (<@{team.creator_id}>)")
            
            # 나머지 멤버들 추가
            for member in members:
                member_name = member.user_name
                member_list.append(f"• {member.position}: {member_name} (<@{member.user_id}>)")
            
            return {
                "success": True,
                "team_name": team_name,
                "members": member_list,
                "position_counts": position_counts,
                "team_type": team_type,
                "required_composition": required_composition,
                "created_at": team.created_at.strftime("%Y-%m-%d %H:%M"),
                "creator_name": creator_name,
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
            team_count_5 = 0
            team_count_4 = 0
            
            for team in teams:
                members = self.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
                member_count = len(members)
                
                # 팀 유형 분류 (포지션 제한 없이 인원수만으로 판단)
                if member_count >= 5:
                    team_type = "5인팀"
                    total_required = 5
                    team_count_5 += 1
                elif member_count >= 4:
                    team_type = "4인팀"
                    total_required = 4
                    team_count_4 += 1
                else:
                    team_type = "구성중"
                    total_required = 5  # 기본값
                
                team_list.append({
                    "name": team.name,
                    "member_count": member_count,
                    "total_required": total_required,
                    "team_type": team_type,
                    "is_complete": member_count >= total_required,
                    "created_at": team.created_at.strftime("%Y-%m-%d %H:%M")
                })
            
            # 팀 제한 정보 추가
            limit_info = {
                "team_count_5": team_count_5,
                "team_count_4": team_count_4,
                "max_teams_5": MAX_TEAMS_5,
                "max_teams_4": MAX_TEAMS_4
            }
            
            return {"success": True, "teams": team_list, "limit_info": limit_info}
            
        except Exception as e:
            logger.error(f"Error getting all teams: {e}")
            return {"success": False, "message": "팀 목록 조회 중 오류가 발생했습니다."}
    
    def get_user_team(self, user_id: str) -> dict:
        """사용자가 속한 팀 조회 (Slack User ID 기준)"""
        try:
            member = self.db.query(TeamMember).filter(TeamMember.user_id == user_id).first()
            if not member:
                return {"success": False, "message": f"<@{user_id}>님은 어떤 팀에도 속해있지 않습니다."}
            
            team = self.db.query(Team).filter(Team.id == member.team_id, Team.is_active == True).first()
            if not team:
                return {"success": False, "message": "팀 정보를 찾을 수 없습니다."}
            
            return {
                "success": True,
                "team": {
                    "name": team.name,
                    "creator_id": team.creator_id,
                    "creator_name": team.creator_name,
                    "position": member.position,
                    "joined_at": member.joined_at.strftime("%Y-%m-%d %H:%M")
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting user team: {e}")
            return {"success": False, "message": "사용자 팀 정보 조회 중 오류가 발생했습니다."} 