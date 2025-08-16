import os
import hmac
import hashlib
import json
import requests
import logging
import urllib.parse
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .models import get_db, MAX_TEAMS_5, MAX_TEAMS_4, POSITIONS, Team, TeamMember
from .team_service import TeamBuildingService
from .user_service import UserService
from .topic_service import TopicSelectionService
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

def get_user_info(user_id: str) -> dict:
    """Slack API를 통해 사용자 정보를 가져옵니다"""
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not found, cannot get user info")
        return {"is_staff": False, "is_admin": False}
    
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
                # staff 또는 admin 권한 확인
                is_staff = user.get("is_admin", False) or user.get("is_owner", False)
                is_admin = user.get("is_admin", False) or user.get("is_owner", False)
                
                logger.info(f"User {user_id} info: is_staff={is_staff}, is_admin={is_admin}")
                return {"is_staff": is_staff, "is_admin": is_admin}
        
        logger.warning(f"Failed to get user info for {user_id}: {response.text}")
        return {"is_staff": False, "is_admin": False}
        
    except Exception as e:
        logger.error(f"Error getting user info for {user_id}: {e}")
        return {"is_staff": False, "is_admin": False}

def verify_slack_request(body: bytes, signature: str, timestamp: str):
    """Slack 요청 서명 검증"""
    if not SLACK_SIGNING_SECRET:
        logger.warning("SLACK_SIGNING_SECRET not found, skipping verification")
        return
    
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    my_sig = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(my_sig, signature):
        raise HTTPException(status_code=400, detail="Invalid Slack signature")

def get_slack_user_id_by_name(user_name: str) -> str:
    """Slack API를 통해 사용자명으로 User ID를 가져옵니다"""
    logger.info(f"=== get_slack_user_id_by_name called ===")
    logger.info(f"Searching for user_name: '{user_name}'")
    
    if not user_name:
        logger.warning("Empty user_name provided")
        return None
    
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not found, cannot get user ID by name")
        return None

    try:
        # 먼저 users.search API를 시도
        logger.info("Making request to Slack API users.search")
        search_response = requests.get(
            "https://slack.com/api/users.search",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"query": user_name}
        )
        
        logger.info(f"Search response status: {search_response.status_code}")
        if search_response.status_code == 200:
            search_data = search_response.json()
            logger.info(f"Search response ok: {search_data.get('ok')}")
            logger.info(f"Search response error: {search_data.get('error')}")
            
            if search_data.get("ok"):
                search_users = search_data.get("users", {}).get("matches", [])
                logger.info(f"Found {len(search_users)} users in search")
                
                for user in search_users:
                    user_name_slack = user.get("name")
                    real_name_slack = user.get("real_name")
                    display_name_slack = user.get("display_name")
                    
                    logger.info(f"Search result user: name='{user_name_slack}', real_name='{real_name_slack}', display_name='{display_name_slack}'")
                    
                    if user_name_slack == user_name or real_name_slack == user_name or display_name_slack == user_name:
                        user_id = user.get("id")
                        logger.info(f"Found exact matching user in search! ID: {user_id}")
                        return user_id
                    
                    # 부분 문자열 매칭도 시도
                    if (user_name_slack and user_name in user_name_slack) or \
                       (real_name_slack and user_name in real_name_slack) or \
                       (display_name_slack and user_name in display_name_slack):
                        user_id = user.get("id")
                        logger.info(f"Found partial matching user in search! ID: {user_id}")
                        return user_id

        # users.search가 실패하면 users.list를 시도
        logger.info("Making request to Slack API users.list")
        response = requests.get(
            "https://slack.com/api/users.list",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        )

        logger.info(f"Response status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            logger.info(f"Response ok: {data.get('ok')}")
            logger.info(f"Response error: {data.get('error')}")
            
            if data.get("ok"):
                users = data.get("users", [])
                logger.info(f"Found {len(users)} users in workspace")
                
                # 모든 사용자 정보 로깅 (디버깅용)
                for i, user in enumerate(users[:10]):  # 처음 10명 로깅
                    logger.info(f"User {i+1}: name='{user.get('name')}', real_name='{user.get('real_name')}', display_name='{user.get('display_name')}', id='{user.get('id')}'")
                
                for user in users:
                    user_name_slack = user.get("name")
                    real_name_slack = user.get("real_name")
                    display_name_slack = user.get("display_name")
                    
                    logger.info(f"Checking user: name='{user_name_slack}', real_name='{real_name_slack}', display_name='{display_name_slack}' against search='{user_name}'")
                    
                    if user_name_slack == user_name or real_name_slack == user_name or display_name_slack == user_name:
                        user_id = user.get("id")
                        logger.info(f"Found exact matching user! ID: {user_id}")
                        return user_id
                    
                    # 부분 문자열 매칭도 시도
                    if (user_name_slack and user_name in user_name_slack) or \
                       (real_name_slack and user_name in real_name_slack) or \
                       (display_name_slack and user_name in display_name_slack):
                        user_id = user.get("id")
                        logger.info(f"Found partial matching user! ID: {user_id}")
                        return user_id

        logger.warning(f"Failed to find user ID for name: {user_name}")
        return None

    except Exception as e:
        logger.error(f"Error getting user ID by name {user_name}: {e}")
        return None



def parse_slack_mention(text: str) -> tuple:
    """Slack 멘션 형식을 파싱하여 user_id와 user_name을 반환합니다"""
    logger.info(f"parse_slack_mention called with text: '{text}'")
    
    if not text:
        logger.warning("Empty text provided to parse_slack_mention")
        return None, None
    
    # 형식: <@U1234567890|username>
    if text.startswith('<@') and '|' in text and text.endswith('>'):
        parts = text[2:-1].split('|')
        if len(parts) == 2:
            user_id = parts[0]
            user_name = parts[1]
            logger.info(f"Parsed Slack mention format: user_id='{user_id}', user_name='{user_name}'")
            return user_id, user_name
        else:
            logger.warning(f"Invalid Slack mention format: {text}")
            return None, None
    # 형식: @username
    elif text.startswith('@'):
        user_name = text[1:]
        logger.info(f"Parsed @ format: user_name='{user_name}'")
        return None, user_name
    else:
        logger.warning(f"Text does not match Slack mention format: {text}")
        return None, None

def resolve_user_id(target_user_name: str, target_user_id: str = None) -> tuple:
    """사용자 이름이나 ID를 통해 Slack User ID를 해결합니다"""
    logger.info(f"resolve_user_id called - target_user_name: '{target_user_name}', target_user_id: '{target_user_id}'")
    
    if target_user_id:
        # 이미 user_id가 제공된 경우
        logger.info(f"Using provided target_user_id: '{target_user_id}'")
        slack_user_id = target_user_id
        display_name = target_user_name or slack_user_id
        logger.info(f"Resolved with provided ID: slack_user_id='{slack_user_id}', display_name='{display_name}'")
        return slack_user_id, display_name
    else:
        # 이름으로 Slack User ID 찾기
        logger.info(f"Searching for Slack User ID by name: '{target_user_name}'")
        slack_user_id = get_slack_user_id_by_name(target_user_name)
        
        if not slack_user_id:
            logger.warning(f"Failed to find Slack User ID for name: '{target_user_name}'")
            return None, None
        
        # user_name을 그대로 사용
        display_name = target_user_name or slack_user_id
        logger.info(f"Resolved by name search: slack_user_id='{slack_user_id}', display_name='{display_name}'")
        
        return slack_user_id, display_name

@router.post("/commands")
async def handle_slash_commands(
    request: Request,
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...),
    db: Session = Depends(get_db)
):
    body = await request.body()
    verify_slack_request(body, x_slack_signature, x_slack_request_timestamp)
    
    # URL 인코딩된 데이터 파싱
    form_data = body.decode('utf-8')
    params = {}
    for item in form_data.split('&'):
        if '=' in item:
            key, value = item.split('=', 1)
            # URL 디코딩
            key = urllib.parse.unquote(key)
            value = urllib.parse.unquote(value)
            params[key] = value
    
    command = params.get('command', '')
    text = params.get('text', '').strip()
    user_id = params.get('user_id', '')
    user_name = params.get('user_name', '')
    
    logger.info(f"Slash command received: {command} {text} by {user_name}")
    logger.info(f"Raw form data: {form_data}")
    logger.info(f"Parsed params: {params}")
    
    # 디버깅을 위한 추가 로그
    logger.info(f"=== DEBUG INFO ===")
    logger.info(f"command type: {type(command)}")
    logger.info(f"command value: '{command}'")
    logger.info(f"command == '/사용자정보': {command == '/사용자정보'}")
    logger.info(f"command == '/사용자정보': {repr(command) == repr('/사용자정보')}")
    logger.info(f"command length: {len(command) if command else 0}")
    logger.info(f"command bytes: {command.encode('utf-8') if command else b''}")
    logger.info(f"==================")
    
    team_service = TeamBuildingService(db)
    user_service = UserService(db)
    
    # 사용자 ID 자동 업데이트 (임의 ID를 실제 Slack User ID로 변경)
    if user_id and user_name:
        update_result = user_service.update_user_slack_id(user_name, user_id)
        if update_result["success"]:
            logger.info(f"User ID updated for {user_name}: {update_result['message']}")
    
    if command == '/팀생성':
        logger.info("Calling handle_create_team")
        return handle_create_team(text, user_id, user_name, team_service)
    elif command == '/팀빌딩':
        logger.info("Calling handle_add_member")
        return handle_add_member(text, user_id, user_name, team_service)
    elif command == '/팀정보':
        logger.info("Calling handle_team_info")
        return handle_team_info(text, team_service)
    elif command == '/팀목록':
        logger.info("Calling handle_team_list")
        return handle_team_list(team_service)
    elif command == '/팀삭제':
        logger.info("Calling handle_delete_team")
        return handle_delete_team(text, user_id, user_name, team_service)
    elif command == '/팀원삭제':
        logger.info("Calling handle_remove_member")
        return handle_remove_member(text, user_id, user_name, team_service)
    elif command == '/사용자정보':
        logger.info("Calling handle_user_info")
        return handle_user_info(text, user_service)
    elif command == '/사용자목록':
        logger.info("Calling handle_user_list")
        return handle_user_list(user_service)
    elif command == '/자기소개':
        logger.info("Calling handle_self_introduction")
        return handle_self_introduction(user_id, user_name, user_service)
    elif command == '/주제선정':
        logger.info("Calling handle_topic_selection")
        return handle_topic_selection(text, user_id, user_name, team_service)
    elif command == '/주제목록':
        logger.info("Calling handle_topic_list")
        return handle_topic_list(team_service)
    elif command == '/명령어':
        logger.info("Calling handle_help_command")
        return handle_help_command()
    else:
        logger.warning(f"Unknown command: {command}")
        return {
            "response_type": "ephemeral",
            "text": f"알 수 없는 명령어입니다: {command}"
        }

def handle_create_team(text: str, user_id: str, user_name: str, team_service: TeamBuildingService):
    """팀 생성 처리"""
    if not text:
        help_text = "사용법: `/팀생성 팀명`\n예시: `/팀생성 해커톤팀1`\n\n"
        help_text += "📊 *팀 구성 제한*\n"
        help_text += f"• 5인팀: 최대 {MAX_TEAMS_5}팀 (최대 5명, 포지션 제한 없음)\n"
        help_text += f"• 4인팀: 최대 {MAX_TEAMS_4}팀 (최대 4명, 포지션 제한 없음)\n"
        return {
            "response_type": "ephemeral",
            "text": help_text
        }
    
    # user_id를 직접 사용하고, user_name을 creator_name으로 사용
    creator_name = user_name
    
    result = team_service.create_team(text, user_id, creator_name)
    
    if result["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"🎉 {result['message']}\n팀장: <@{user_id}> ({creator_name})"
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_add_member(text: str, user_id: str, user_name: str, team_service: TeamBuildingService):
    """팀원 추가 처리 - 팀장의 팀에 팀원 추가"""
    logger.info(f"=== handle_add_member called ===")
    logger.info(f"text parameter: '{text}'")
    logger.info(f"user_id: '{user_id}'")
    logger.info(f"user_name: '{user_name}'")
    
    if not text:
        help_text = "사용법: `/팀빌딩 @유저명`\n"
        help_text += "팀장만 사용 가능합니다. 팀원을 추가합니다.\n\n"
        help_text += "📊 *팀 구성 제한*\n"
        help_text += f"• 5인팀: 최대 {MAX_TEAMS_5}팀 (최대 5명, 포지션 제한 없음)\n"
        help_text += f"• 4인팀: 최대 {MAX_TEAMS_4}팀 (최대 4명, 포지션 제한 없음)\n"
        return {
            "response_type": "ephemeral",
            "text": help_text
        }
    
    # Slack 멘션 형식 처리
    target_user_id, target_user_name = parse_slack_mention(text)
    logger.info(f"Parsed mention - target_user_id: '{target_user_id}', target_user_name: '{target_user_name}'")
    
    if not target_user_id and not target_user_name:
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작하거나 Slack 멘션 형식이어야 합니다.\n사용법: `/팀빌딩 @홍길동` 또는 멘션으로 선택"
        }
    
    # 팀장의 팀 찾기
    logger.info(f"Searching for team with creator_id: '{user_id}'")
    team = team_service.db.query(Team).filter(Team.creator_id == user_id, Team.is_active == True).first()
    
    if not team:
        logger.warning(f"No team found for creator_id: '{user_id}'")
        
        # 사용자가 속한 팀이 있는지 확인 (팀원으로)
        user_teams = team_service.db.query(TeamMember).filter(TeamMember.user_id == user_id).all()
        if user_teams:
            team_names = []
            for member in user_teams:
                team_obj = team_service.db.query(Team).filter(Team.id == member.team_id).first()
                if team_obj:
                    team_names.append(team_obj.name)
            
            if team_names:
                return {
                    "response_type": "ephemeral",
                    "text": f"❌ 팀장으로 생성한 팀이 없습니다.\n현재 '{', '.join(team_names)}' 팀의 팀원입니다.\n\n팀원 추가는 팀장만 할 수 있습니다.\n팀을 새로 만들려면 `/팀생성 팀명`으로 팀을 생성해주세요."
                }
        
        # 팀장으로 생성한 팀이 없는 경우
        return {
            "response_type": "ephemeral",
            "text": f"❌ 팀장으로 생성한 팀이 없습니다.\n먼저 `/팀생성 팀명`으로 팀을 생성해주세요.\n\n사용법: `/팀생성 해커톤팀1`"
        }
    
    logger.info(f"Found team: id={team.id}, name='{team.name}', creator_id='{team.creator_id}'")
    
    # 사용자 ID 해결
    slack_user_id, display_name = resolve_user_id(target_user_name, target_user_id)
    logger.info(f"Resolved user - slack_user_id: '{slack_user_id}', display_name: '{display_name}'")
    
    if not slack_user_id:
        return {
            "response_type": "ephemeral",
            "text": f"❌ 사용자 '{target_user_name}'을(를) 찾을 수 없습니다.\nSlack 워크스페이스에 존재하는 사용자인지 확인해주세요."
        }
    
    # 팀원 추가 (포지션은 자동으로 결정)
    if team and hasattr(team, 'name') and team.name:
        logger.info(f"Adding member to team: team.name='{team.name}', slack_user_id='{slack_user_id}', display_name='{display_name}'")
        result = team_service.add_member_to_team(team.name, slack_user_id, display_name)
        
        if result["success"]:
            return {
                "response_type": "ephemeral",
                "text": f"✅ {result['message']}\n추가된 멤버: <@{slack_user_id}> ({display_name})"
            }
        else:
            return {
                "response_type": "ephemeral",
                "text": f"❌ {result['message']}"
            }
    else:
        logger.error(f"Invalid team object: {team}")
        return {
            "response_type": "ephemeral",
            "text": "❌ 팀 정보를 가져오는 중 오류가 발생했습니다. 다시 시도해주세요."
        }

def handle_user_info(text: str, user_service: UserService):
    """사용자 정보 조회 처리"""
    logger.info(f"=== handle_user_info called ===")
    logger.info(f"text parameter: '{text}'")
    
    if not text:
        logger.warning("No text provided")
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/사용자정보 @유저명`\n예시: `/사용자정보 @홍길동`"
        }
    
    # Slack 멘션 형식 처리
    user_id, user_name = parse_slack_mention(text)
    
    if not user_id and not user_name:
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/사용자정보 @홍길동`"
        }
    
    # 사용자 ID 해결
    slack_user_id, display_name = resolve_user_id(user_name, user_id)
    
    if not slack_user_id:
        return {
            "response_type": "ephemeral",
            "text": f"❌ 사용자 '{user_name}'을(를) 찾을 수 없습니다.\nSlack 워크스페이스에 존재하는 사용자인지 확인해주세요."
        }
    
    # Slack User ID로 정보 조회
    result = user_service.get_user_info(slack_user_id)
    
    if result["success"]:
        user = result["user"]
        response_text = f"👤 *{user['name']}* 사용자 정보\n"
        response_text += f"Slack ID: <@{user['user_id']}>\n"
        response_text += f"학교/전공: {user['school_major'] or '미입력'}\n"
        response_text += f"포지션: {user['position'] or '미입력'}\n"
        response_text += f"4대보험: {user['insurance'] or '미입력'}\n"
        response_text += f"이메일: {user['email'] or '미입력'}\n"
        response_text += f"등록일: {user['created_at']}"
        
        return {
            "response_type": "ephemeral",
            "text": response_text
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}\n사용자가 데이터베이스에 등록되어 있지 않습니다."
        }

def handle_user_list(user_service: UserService):
    """사용자 목록 조회 처리"""
    
    # 기존 로직 (Slack API 실패 시)
    result = user_service.get_all_users()
    
    if result["success"]:
        if not result["users"]:
            return {
                "response_type": "ephemeral",
                "text": "👥 *사용자 목록*\n아직 등록된 사용자가 없습니다.\n`/사용자등록`으로 사용자를 등록해보세요!"
            }
        
        response_text = "👥 *사용자 목록*\n"
        for user in result["users"]:
            response_text += f"• *{user['name']}* (<@{user['user_id']}>)\n"
            response_text += f"  포지션: {user['position'] or '미입력'}\n"
            response_text += f"  학교/전공: {user['school_major'] or '미입력'}\n"
            response_text += f"  4대보험: {user['insurance'] or '미입력'}\n\n"
        
        return {
            "response_type": "ephemeral",
            "text": response_text
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_team_info(text: str, team_service: TeamBuildingService):
    """팀 정보 조회 처리"""
    if not text:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀정보 팀명`\n예시: `/팀정보 해커톤팀1`"
        }
    
    result = team_service.get_team_info(text)
    
    if result["success"]:
        team_type = result.get("team_type", "구성중")
        response_text = f"📋 *{result['team_name']}* 팀 정보 ({team_type})\n"
        response_text += f"생성일: {result['created_at']}\n"
        response_text += f"팀장: <@{result['creator_id']}> ({result['creator_name']})\n\n"
        
        response_text += "👥 *팀 구성 현황*\n"
        for position, count in result["position_counts"].items():
            response_text += f"• {position}: {count}명\n"
        
        if result["members"]:
            response_text += "\n*팀 멤버*\n"
            response_text += "\n".join(result["members"])
        else:
            response_text += "\n*팀 멤버*: 아직 없음"
        
        return {
            "response_type": "ephemeral",
            "text": response_text
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_team_list(team_service: TeamBuildingService):
    """팀 목록 조회 처리"""
    result = team_service.get_all_teams()
    
    if result["success"]:
        if not result["teams"]:
            return {
                "response_type": "ephemeral",
                "text": "📋 *팀 목록*\n아직 생성된 팀이 없습니다.\n`/팀생성 팀명`으로 팀을 만들어보세요!"
            }
        
        response_text = "📋 *팀 목록*\n"
        
        # 팀 제한 정보 표시
        limit_info = result.get("limit_info", {})
        response_text += f"📊 *팀 구성 현황*\n"
        response_text += f"• 5인팀: {limit_info.get('team_count_5', 0)}/{limit_info.get('max_teams_5', 10)}팀\n"
        response_text += f"• 4인팀: {limit_info.get('team_count_4', 0)}/{limit_info.get('max_teams_4', 2)}팀\n\n"
        
        for team in result["teams"]:
            status_emoji = "✅" if team["is_complete"] else "⏳"
            team_type = team.get("team_type", "구성중")
            response_text += f"{status_emoji} *{team['name']}* ({team['member_count']}/{team['total_required']}명) - {team_type}\n"
            response_text += f"   생성일: {team['created_at']}\n\n"
        
        return {
            "response_type": "ephemeral",
            "text": response_text
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        } 

def handle_delete_team(text: str, user_id: str, user_name: str, team_service: TeamBuildingService):
    """팀 삭제 처리"""
    if not text:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀삭제 팀명`\n예시: `/팀삭제 해커톤팀1`"
        }
    
    # 사용자 권한 확인
    user_info = get_user_info(user_id)
    is_staff = user_info.get("is_staff", False)
    
    result = team_service.delete_team(text, user_id, is_staff=is_staff)
    
    if result["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"✅ {result['message']}"
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_remove_member(text: str, user_id: str, user_name: str, team_service: TeamBuildingService):
    """팀원 삭제 처리"""
    if not text:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀원삭제 팀명 @유저명`\n예시: `/팀원삭제 해커톤팀1 @홍길동`"
        }
    
    parts = text.split()
    if len(parts) != 2:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀원삭제 팀명 @유저명`\n예시: `/팀원삭제 해커톤팀1 @홍길동`"
        }
    
    team_name, target_user = parts
    
    if not target_user.startswith('@'):
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/팀원삭제 해커톤팀1 @홍길동`"
        }
    
    # Slack 멘션 형식 처리
    target_user_id, target_user_name = parse_slack_mention(target_user)
    
    if not target_user_id and not target_user_name:
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/팀원삭제 해커톤팀1 @홍길동`"
        }
    
    # 사용자 ID 해결
    slack_user_id, display_name = resolve_user_id(target_user_name, target_user_id)
    
    if not slack_user_id:
        return {
            "response_type": "ephemeral",
            "text": f"❌ 사용자 '{target_user_name}'을(를) 찾을 수 없습니다.\nSlack 워크스페이스에 존재하는 사용자인지 확인해주세요."
        }
    
    # 사용자 권한 확인
    user_info = get_user_info(user_id)
    is_staff = user_info.get("is_staff", False)
    
    result = team_service.remove_member_from_team(team_name, slack_user_id, user_id, is_staff=is_staff)
    
    if result["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"✅ {result['message']}\n삭제된 멤버: <@{slack_user_id}> ({display_name})"
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_help_command():
    """명령어 도움말 처리"""
    help_text = "🤖 *팀빌딩 봇 명령어 가이드*\n\n"
    
    help_text += "📋 *팀 관리 명령어*\n"
    help_text += "• `/팀생성 팀명` - 새로운 팀을 생성합니다\n"
    help_text += "  예시: `/팀생성 해커톤팀1`\n\n"
    
    help_text += "• `/팀빌딩 @유저명` - 팀원을 추가합니다 (팀장만 가능)\n"
    help_text += "  팀장의 팀에 팀원을 추가합니다. 포지션은 자동으로 결정됩니다.\n"
    help_text += "  가능한 포지션: BE, FE, Designer, Planner\n"
    help_text += "  *포지션 제한 없음* - 자유롭게 구성 가능\n"
    help_text += "\n"
    
    help_text += "• `/팀정보 팀명` - 팀의 상세 정보를 조회합니다\n"
    help_text += "  예시: `/팀정보 해커톤팀1`\n\n"
    
    help_text += "• `/팀목록` - 모든 팀 목록을 조회합니다\n\n"
    
    help_text += "• `/팀삭제 팀명` - 팀을 삭제합니다 (팀장 또는 관리자만 가능)\n"
    help_text += "  예시: `/팀삭제 해커톤팀1`\n\n"
    
    help_text += "• `/팀원삭제 팀명 @유저명` - 팀에서 멤버를 삭제합니다 (팀장 또는 관리자만 가능)\n"
    help_text += "  예시: `/팀원삭제 해커톤팀1 @홍길동`\n\n"
    
    help_text += "📋 *주제선정 명령어*\n"
    help_text += "• `/주제선정 WORK/RUN` - 팀의 주제를 선택합니다 (팀장만 가능)\n"
    help_text += "  예시: `/주제선정 WORK` 또는 `/주제선정 run`\n"
    help_text += "  규칙: 한국 시간 15:30 이후, 각 주제별 최대 6팀, 대소문자 구분 없음\n\n"
    
    help_text += "• `/주제목록` - 모든 팀의 주제선정 현황을 조회합니다\n\n"
    
    help_text += "👤 *사용자 조회 명령어*\n"
    help_text += "• `/사용자정보 @유저명` - 사용자 정보를 조회합니다\n"
    help_text += "  예시: `/사용자정보 @홍길동`\n\n"
    
    help_text += "• `/사용자목록` - 모든 사용자 목록을 조회합니다\n\n"
    
    help_text += "• `/자기소개` - 자기소개 템플릿을 생성합니다\n"
    help_text += "  DB에 등록된 정보를 기반으로 템플릿을 제공합니다\n\n"
    
    help_text += "📊 *팀 구성*\n"
    help_text += "• 팀장 1명 + 팀원들로 구성\n"
    help_text += "• 가능한 포지션: BE, FE, Designer, Planner\n"
    help_text += "• 포지션 제한 없음 - 자유롭게 구성 가능\n"
    help_text += "• 팀 제한: 5인팀 최대 10팀, 4인팀 최대 2팀\n"
    
    help_text += "💡 *사용 팁*\n"
    help_text += "• 팀명은 중복될 수 없습니다\n"
    help_text += "• 한 명은 하나의 팀에만 속할 수 있습니다\n"
    
    help_text += "🔧 *문제 해결*\n"
    help_text += "• 명령어가 작동하지 않으면 봇을 채널에 초대해주세요\n"
    help_text += "• 권한 문제가 있다면 관리자에게 문의하세요\n\n"
    
    help_text += "즐거운 해커톤 되세요! 🚀"
    
    return {
        "response_type": "ephemeral",
        "text": help_text
    }

def handle_self_introduction(user_id: str, user_name: str, user_service: UserService):
    """자기소개 템플릿 생성"""
    logger.info(f"=== handle_self_introduction called ===")
    logger.info(f"user_id: {user_id}, user_name: {user_name}")
    
    # 사용자 정보 조회 (Slack ID 기준)
    result = user_service.get_user_info(user_id)
    
    if not result["success"]:
        # user_id로 찾지 못했으면 user_name 사용
        logger.warning(f"Could not find user by user_id: {user_id}, using user_name: {user_name}")
        search_name = user_name
        
        # 모든 사용자를 가져와서 display_name으로 검색
        all_users_result = user_service.get_all_users()
        if all_users_result["success"]:
            for user in all_users_result["users"]:
                if user['name'] == search_name:
                    logger.info(f"Found user by name: {search_name}")
                    user_info = user
                    break
            else:
                logger.info(f"No user found with name: {search_name}")
                user_info = None
        else:
            logger.error(f"Failed to get all users: {all_users_result['message']}")
            user_info = None
    else:
        user_info = result["user"]
    
    # 자기소개 템플릿 생성
    if user_info:
        # DB에 있는 정보로 기본값 설정
        name = user_info['name']
        school_major = user_info['school_major'] or ''
        position = user_info['position'] or ''
        insurance = user_info['insurance'] or ''
        
        # 포지션에 따른 개발 분야 안내
        dev_field_guide = ""
        if position in ['백엔드', '프론트엔드']:
            dev_field_guide = f"*개발 분야*: (예: {position} 개발, 웹 개발, 모바일 앱 개발 등)\n"
        
        template = f"""📝 *자기소개 템플릿*

*이름*: {name}
*소속*: {school_major}
*포지션*: {position}
{dev_field_guide}*4대 보험 가입 여부*: {insurance}
*MBTI*: (예: INTJ, ENFP 등)
*자기소개*: (자유롭게 작성해주세요)

💡 *작성 팁*
• 간결하고 명확하게 작성해주세요
• 자신의 강점과 경험을 포함해보세요
• 팀워크나 협업 경험이 있다면 언급해보세요
• 해커톤에서 하고 싶은 프로젝트가 있다면 간단히 소개해보세요"""
        
        return {
            "response_type": "ephemeral",
            "text": template
        }

def handle_topic_selection(text: str, user_id: str, user_name: str, team_service: TeamBuildingService):
    """주제선정 처리"""
    if not text:
        help_text = "사용법: `/주제선정 WORK` 또는 `/주제선정 RUN`\n"
        help_text += "팀장만 사용 가능합니다.\n\n"
        help_text += "📋 *주제선정 규칙*\n"
        help_text += "• 한국 시간 15:30 이후에만 가능\n"
        help_text += "• 팀장만 선택 가능\n"
        help_text += "• 각 주제별 최대 6팀까지 가능\n"
        help_text += "• WORK와 RUN 중 선택\n"
        help_text += "• 대소문자 구분 없음\n"
        help_text += "• 변경 가능 (아직 다 차지 않았다면)\n\n"
        help_text += "예시: `/주제선정 WORK` 또는 `/주제선정 run`"
        return {
            "response_type": "ephemeral",
            "text": help_text
        }
    
    # 팀장의 팀 찾기
    team = team_service.db.query(Team).filter(Team.creator_id == user_id, Team.is_active == True).first()
    
    if not team:
        return {
            "response_type": "ephemeral",
            "text": "❌ 팀장으로 생성한 팀이 없습니다.\n먼저 `/팀생성 팀명`으로 팀을 생성해주세요."
        }
    
    # 주제선정 서비스 생성
    topic_service = TopicSelectionService(team_service.db)
    
    # 주제선정 실행
    result = topic_service.select_topic(team.name, text, user_id, user_name)
    
    if result["success"]:
        # 현재 주제별 팀 수 조회
        topic_counts = topic_service.get_topic_counts()
        if topic_counts["success"]:
            count_info = f"\n\n📊 *현재 주제별 선택 현황*\n"
            count_info += f"• WORK: {topic_counts['work_count']}/6팀\n"
            count_info += f"• RUN: {topic_counts['run_count']}/6팀"
        else:
            count_info = ""
        
        return {
            "response_type": "ephemeral",
            "text": f"✅ {result['message']}{count_info}"
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_topic_list(team_service: TeamBuildingService):
    """주제선정 목록 조회 처리"""
    topic_service = TopicSelectionService(team_service.db)
    
    # 주제별 팀 수 조회
    topic_counts = topic_service.get_topic_counts()
    if not topic_counts["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {topic_counts['message']}"
        }
    
    # 모든 주제선정 정보 조회
    all_selections = topic_service.get_all_topic_selections()
    if not all_selections["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {all_selections['message']}"
        }
    
    response_text = "📋 *주제선정 현황*\n\n"
    response_text += f"📊 *주제별 선택 현황*\n"
    response_text += f"• WORK: {topic_counts['work_count']}/6팀"
    if not topic_counts['work_available']:
        response_text += " (마감)"
    response_text += f"\n• RUN: {topic_counts['run_count']}/6팀"
    if not topic_counts['run_available']:
        response_text += " (마감)"
    response_text += "\n\n"
    
    if all_selections["selections"]:
        response_text += "🏆 *선택된 팀 목록*\n"
        for selection in all_selections["selections"]:
            response_text += f"• *{selection['team_name']}* - {selection['topic']} (팀장: {selection['creator_name']})\n"
    else:
        response_text += "🏆 *선택된 팀 목록*\n아직 주제를 선택한 팀이 없습니다."
    
    return {
        "response_type": "ephemeral",
        "text": response_text
    }