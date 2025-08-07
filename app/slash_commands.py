import os
import hmac
import hashlib
import json
import requests
import logging
import urllib.parse
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .models import get_db, TEAM_COMPOSITION, POSITIONS, Team, TeamMember
from .team_service import TeamBuildingService
from .user_service import UserService
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
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not found, cannot get user ID by name")
        return None

    try:
        response = requests.get(
            "https://slack.com/api/users.list",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                users = data.get("users", [])
                for user in users:
                    if user.get("name") == user_name or user.get("real_name") == user_name:
                        return user.get("id")

        logger.warning(f"Failed to find user ID for name: {user_name}")
        return None

    except Exception as e:
        logger.error(f"Error getting user ID by name {user_name}: {e}")
        return None

def get_slack_user_display_name(user_id: str) -> str:
    """Slack API를 통해 User ID로 실제 표시 이름을 가져옵니다"""
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not found, cannot get user display name")
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
                logger.info(f"Found display name for {user_id}: {display_name}")
                return display_name

        logger.warning(f"Failed to find display name for user ID: {user_id}")
        return None

    except Exception as e:
        logger.error(f"Error getting display name for user ID {user_id}: {e}")
        return None

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
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀생성 팀명`\n예시: `/팀생성 해커톤팀1`"
        }
    
    # 팀장의 display_name 가져오기
    creator_display_name = get_slack_user_display_name(user_id)
    if creator_display_name:
        creator_name = creator_display_name
    else:
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
    if not text:
        help_text = "사용법: `/팀빌딩 @유저명`\n"
        help_text += "팀장만 사용 가능합니다. 팀원을 추가합니다."
        return {
            "response_type": "ephemeral",
            "text": help_text
        }
    
    # @로 시작하는지 확인
    if not text.startswith('@'):
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n사용법: `/팀빌딩 @홍길동`"
        }
    
    # 팀장의 팀 찾기
    team = team_service.db.query(Team).filter(Team.creator_id == user_id, Team.is_active == True).first()
    if not team:
        return {
            "response_type": "ephemeral",
            "text": f"❌ 팀장으로 생성한 팀이 없습니다.\n먼저 `/팀생성 팀명`으로 팀을 생성해주세요."
        }
    
    # Slack 멘션 형식 처리: <@U1234567890|username> 또는 @username
    target_user_id = None
    target_user_name = None
    
<<<<<<< HEAD
    if text.startswith('<@') and '|' in text and text.endswith('>'):
        # 형식: <@U1234567890|username>
        parts = text[2:-1].split('|')
        if len(parts) == 2:
            target_user_id = parts[0]
            target_user_name = parts[1]
    elif text.startswith('@'):
        # 형식: @username
        target_user_name = text[1:]
    else:
=======
    # 현재 팀 구성 현황
    members = team_service.db.query(TeamMember).filter(TeamMember.team_id == team.id).all()
    message_text += "📊 *현재 팀 구성*\n"
    
    # 포지션별 현재 인원수 계산 (팀장 포함)
    position_counts = {}
    for member in members:
        position = member.position
        if position not in position_counts:
            position_counts[position] = 0
        position_counts[position] += 1
    
    # 팀장의 포지션을 확인하고 카운트에 추가
    from .user_service import UserService
    user_service = UserService(team_service.db)
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
    
    for position, count in position_counts.items():
        message_text += f"• {position}: {count}명\n"
    
    message_text += "\n👥 *현재 멤버*\n"
    # 팀장을 먼저 표시
    creator_display_name = get_slack_user_display_name(team.creator_id)
    creator_name = creator_display_name if creator_display_name else team.creator_name
    message_text += f"• 팀장: <@{team.creator_id}> ({creator_name})\n"
    
    if members:
        for member in members:
            display_name = get_slack_user_display_name(member.user_id)
            member_name = display_name if display_name else member.user_name
            message_text += f"• <@{member.user_id}> ({member_name}) - {member.position}\n"
    else:
        message_text += "아직 추가 멤버가 없습니다.\n"
    
    message_text += "\n🎉 *팀에 합류하고 싶다면 스레드에 댓글을 남겨주세요!*\n"
    message_text += "댓글 형식: `@유저명` 또는 `@유저명 포지션`\n"
    message_text += "예시: `@홍길동` 또는 `@홍길동 백엔드`\n\n"
    
    message_text += "📋 *가능한 포지션*\n"
    message_text += "• BE (백엔드)\n"
    message_text += "• FE (프론트엔드)\n"
    message_text += "• Designer (디자인)\n"
    message_text += "• Planner (기획)\n"
    
    # Slack Web API를 사용하여 채널에 메시지 전송
    try:
        headers = {
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # 현재 채널 ID를 가져오기 위해 임시로 ephemeral 응답을 보내고, 
        # 실제 메시지는 별도로 전송
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            json={
                "channel": "C099TRKQ2LQ",  # team-building 채널 ID (하드코딩)
                "text": message_text
            },
            headers=headers
        )
        
        if response.status_code == 200 and response.json().get("ok"):
            return {
                "response_type": "ephemeral",
                "text": f"✅ '{team_name}' 팀빌딩 메시지가 채널에 게시되었습니다!"
            }
        else:
            logger.error(f"Failed to post message: {response.text}")
            return {
                "response_type": "ephemeral",
                "text": f"❌ 메시지 전송에 실패했습니다. 다시 시도해주세요."
            }
            
    except Exception as e:
        logger.error(f"Error posting message: {e}")
>>>>>>> b9235a4edbc661c000faf6b0570b0507bf647a80
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n사용법: `/팀빌딩 @홍길동`"
        }
    
    # target_user_id가 있으면 바로 사용, 없으면 이름으로 찾기
    if target_user_id:
        slack_user_id = target_user_id
    else:
        # 이름으로 Slack User ID 찾기
        slack_user_id = get_slack_user_id_by_name(target_user_name)
        if not slack_user_id:
            return {
                "response_type": "ephemeral",
                "text": f"❌ 사용자 '{target_user_name}'을(를) 찾을 수 없습니다.\nSlack 워크스페이스에 존재하는 사용자인지 확인해주세요."
            }
    
    # Slack User ID로 실제 한글 닉네임 가져오기
    display_name = get_slack_user_display_name(slack_user_id)
    if display_name:
        member_name = display_name
    else:
        member_name = target_user_name or slack_user_id
    
    # 팀원 추가 (포지션은 자동으로 결정)
    result = team_service.add_member_to_team(team.name, slack_user_id, member_name)
    
    if result["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"✅ {result['message']}\n추가된 멤버: <@{slack_user_id}> ({member_name})"
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_user_info(text: str, user_service: UserService):
    """사용자 정보 조회 처리"""
    logger.info(f"=== handle_user_info called ===")
    logger.info(f"text parameter: '{text}'")
    logger.info(f"text type: {type(text)}")
    logger.info(f"text length: {len(text) if text else 0}")
    
    if not text:
        logger.warning("No text provided")
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/사용자정보 @유저명`\n예시: `/사용자정보 @홍길동`"
        }
    
    # Slack 멘션 형식 처리: <@U1234567890|username> 또는 @username
    user_id = None
    user_name = None
    
    if text.startswith('<@') and '|' in text and text.endswith('>'):
        # 형식: <@U1234567890|username>
        parts = text[2:-1].split('|')  # <@ 제거하고 > 제거한 후 |로 분할
        if len(parts) == 2:
            user_id = parts[0]
            user_name = parts[1]
            logger.info(f"Parsed mention format: user_id={user_id}, user_name={user_name}")
    elif text.startswith('@'):
        # 형식: @username
        user_name = text[1:]  # @ 제거
        logger.info(f"Parsed @ format: user_name={user_name}")
    else:
        logger.warning(f"Invalid format: '{text}'")
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/사용자정보 @홍길동`"
        }
    
    # user_id가 있으면 바로 사용, 없으면 이름으로 찾기
    if user_id:
        # user_id가 있으면 바로 사용
        slack_user_id = user_id
        logger.info(f"Using provided user_id: {slack_user_id}")
        
        # Slack User ID로 실제 한글 닉네임 가져오기
        display_name = get_slack_user_display_name(slack_user_id)
        if display_name:
            logger.info(f"Found display name: {display_name} for user_id: {slack_user_id}")
            # 실제 한글 닉네임으로 검색
            search_name = display_name
        else:
            logger.warning(f"Could not get display name for {slack_user_id}, using original user_name: {user_name}")
            search_name = user_name
    else:
        # 이름으로 Slack User ID 찾기
        slack_user_id = get_slack_user_id_by_name(user_name)
        logger.info(f"Found slack_user_id by name: {slack_user_id}")
        
        if not slack_user_id:
            return {
                "response_type": "ephemeral",
                "text": f"❌ 사용자 '{user_name}'을(를) 찾을 수 없습니다.\nSlack 워크스페이스에 존재하는 사용자인지 확인해주세요."
            }
        
        # Slack User ID로 실제 한글 닉네임 가져오기
        display_name = get_slack_user_display_name(slack_user_id)
        if display_name:
            logger.info(f"Found display name: {display_name} for user_id: {slack_user_id}")
            search_name = display_name
        else:
            logger.warning(f"Could not get display name for {slack_user_id}, using original user_name: {user_name}")
            search_name = user_name
    
    # 먼저 user_id로 검색
    result = user_service.get_user_info(slack_user_id)
    
    if not result["success"]:
        # user_id로 찾지 못했으면 한글 닉네임으로 검색
        logger.info(f"User not found by user_id, trying to find by name: {search_name}")
        
        # 모든 사용자를 가져와서 한글 닉네임으로 검색
        all_users_result = user_service.get_all_users()
        logger.info(f"get_all_users result: {all_users_result}")
        
        if all_users_result["success"]:
            logger.info(f"Found {len(all_users_result['users'])} users in database")
            for user in all_users_result["users"]:
                logger.info(f"Checking user: {user['name']} against search name: {search_name}")
                if user['name'] == search_name:
                    logger.info(f"Found user by name: {search_name}")
                    # 찾은 사용자의 정보로 결과 생성
                    user_info = user
                    response_text = f"*{user_info['name']}* 사용자 정보\n"
                    response_text += f"학교/전공: {user_info['school_major'] or '미입력'}\n"
                    response_text += f"포지션: {user_info['position'] or '미입력'}\n"
                    response_text += f"4대보험: {user_info['insurance'] or '미입력'}\n"
                    response_text += f"이메일: {user_info['email'] or '미입력'}\n"
                    
                    return {
                        "response_type": "ephemeral",
                        "text": response_text
                    }
            logger.info(f"No user found with name: {search_name}")
        else:
            logger.error(f"Failed to get all users: {all_users_result['message']}")
    
    # 먼저 이름으로 검색해서 user_id 업데이트
    update_result = user_service.update_user_slack_id(search_name, slack_user_id)
    if update_result["success"]:
        logger.info(f"User ID updated for {search_name}: {update_result['message']}")
    
    # 업데이트된 user_id로 정보 조회
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


    
    # 텍스트 파싱: "BE @홍길동" -> position="BE", target_user="@홍길동"
    parts = text.split()
    if len(parts) != 2:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀빌딩 포지션 @유저명`\n예시: `/팀빌딩 BE @홍길동`"
        }
    
    position, target_user = parts
    
    # @제거하고 user_id 추출
    if not target_user.startswith('@'):
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/팀빌딩 BE @홍길동`"
        }
    
    # 실제 구현에서는 Slack API를 통해 user_id를 가져와야 합니다
    # 여기서는 간단히 target_user를 그대로 사용
    target_user_id = target_user[1:]  # @ 제거
    
    # 팀명을 어떻게 결정할지 - 임시로 첫 번째 팀 사용
    teams_result = team_service.get_all_teams()
    if not teams_result["success"] or not teams_result["teams"]:
        return {
            "response_type": "ephemeral",
            "text": "먼저 팀을 생성해주세요. `/팀생성 팀명`"
        }
    
    team_name = teams_result["teams"][0]["name"]
    result = team_service.add_member_to_team(team_name, position, target_user_id, target_user)
    
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

def handle_team_info(text: str, team_service: TeamBuildingService):
    """팀 정보 조회 처리"""
    if not text:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀정보 팀명`\n예시: `/팀정보 해커톤팀1`"
        }
    
    result = team_service.get_team_info(text)
    
    if result["success"]:
        response_text = f"📋 *{result['team_name']}* 팀 정보\n"
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
        for team in result["teams"]:
            status_emoji = "✅" if team["is_complete"] else "⏳"
            response_text += f"{status_emoji} *{team['name']}* ({team['member_count']}/{team['total_required']}명)\n"
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
    
    # Slack 멘션 형식 처리: <@U1234567890|username> 또는 @username
    target_user_id = None
    target_user_name = None
    
    if target_user.startswith('<@') and '|' in target_user and target_user.endswith('>'):
        # 형식: <@U1234567890|username>
        parts = target_user[2:-1].split('|')
        if len(parts) == 2:
            target_user_id = parts[0]
            target_user_name = parts[1]
    elif target_user.startswith('@'):
        # 형식: @username
        target_user_name = target_user[1:]
    else:
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/팀원삭제 해커톤팀1 @홍길동`"
        }
    
    # target_user_id가 있으면 바로 사용, 없으면 이름으로 찾기
    if target_user_id:
        slack_user_id = target_user_id
    else:
        # 이름으로 Slack User ID 찾기
        slack_user_id = get_slack_user_id_by_name(target_user_name)
        if not slack_user_id:
            return {
                "response_type": "ephemeral",
                "text": f"❌ 사용자 '{target_user_name}'을(를) 찾을 수 없습니다.\nSlack 워크스페이스에 존재하는 사용자인지 확인해주세요."
            }
    
    # Slack User ID로 실제 한글 닉네임 가져오기
    display_name = get_slack_user_display_name(slack_user_id)
    if display_name:
        member_name = display_name
    else:
        member_name = target_user_name or slack_user_id
    
    # 사용자 권한 확인
    user_info = get_user_info(user_id)
    is_staff = user_info.get("is_staff", False)
    
    result = team_service.remove_member_from_team(team_name, slack_user_id, user_id, is_staff=is_staff)
    
    if result["success"]:
        return {
            "response_type": "ephemeral",
            "text": f"✅ {result['message']}\n삭제된 멤버: <@{slack_user_id}> ({member_name})"
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
    
<<<<<<< HEAD
    help_text += "• `/팀빌딩 @유저명` - 팀원을 추가합니다 (팀장만 가능)\n"
    help_text += "  팀장의 팀에 팀원을 추가합니다. 포지션은 자동으로 결정됩니다.\n"
    help_text += "  가능한 포지션:\n"
    for position, count in TEAM_COMPOSITION.items():
        help_text += f"    - {position}: {count}명\n"
    help_text += "\n"
=======
    help_text += "• `/팀빌딩 팀명` - 팀빌딩 메시지를 생성합니다\n"
    help_text += "  예시: `/팀빌딩 해커톤팀1`\n"
    help_text += "  채널에 팀빌딩 메시지를 게시하고, 스레드 댓글로 팀에 합류할 수 있습니다.\n"
    help_text += "  가능한 포지션: BE, FE, Designer, Planner\n\n"
>>>>>>> b9235a4edbc661c000faf6b0570b0507bf647a80
    
    help_text += "• `/팀정보 팀명` - 팀의 상세 정보를 조회합니다\n"
    help_text += "  예시: `/팀정보 해커톤팀1`\n\n"
    
    help_text += "• `/팀목록` - 모든 팀 목록을 조회합니다\n\n"
    
    help_text += "• `/팀삭제 팀명` - 팀을 삭제합니다 (팀장 또는 관리자만 가능)\n"
    help_text += "  예시: `/팀삭제 해커톤팀1`\n\n"
    
    help_text += "• `/팀원삭제 팀명 @유저명` - 팀에서 멤버를 삭제합니다 (팀장 또는 관리자만 가능)\n"
    help_text += "  예시: `/팀원삭제 해커톤팀1 @홍길동`\n\n"
    
    help_text += "👤 *사용자 조회 명령어*\n"
    help_text += "• `/사용자정보 @유저명` - 사용자 정보를 조회합니다\n"
    help_text += "  예시: `/사용자정보 @홍길동`\n\n"
    
    help_text += "• `/사용자목록` - 모든 사용자 목록을 조회합니다\n\n"
    
    help_text += "• `/자기소개` - 자기소개 템플릿을 생성합니다\n"
    help_text += "  DB에 등록된 정보를 기반으로 템플릿을 제공합니다\n\n"
    
    help_text += "📊 *팀 구성*\n"
    help_text += "• 팀장 1명 + 팀원들로 구성\n"
    help_text += "• 가능한 포지션: BE, FE, Designer, Planner\n"
    
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
    
    # 사용자 정보 조회
    result = user_service.get_user_info(user_id)
    
    if not result["success"]:
        # user_id로 찾지 못했으면 한글 닉네임으로 검색
        display_name = get_slack_user_display_name(user_id)
        if display_name:
            logger.info(f"Found display name: {display_name} for user_id: {user_id}")
            search_name = display_name
        else:
            logger.warning(f"Could not get display name for {user_id}, using user_name: {user_name}")
            search_name = user_name
        
        # 모든 사용자를 가져와서 한글 닉네임으로 검색
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
    else:
        # DB에 사용자 정보가 없는 경우 기본 템플릿 제공
        template = f"""📝 *자기소개 템플릿*

*이름*: {user_name}
*소속*: (학교/전공)
*포지션*: (백엔드/프론트엔드/디자인/기획)
*개발 분야*: (백엔드/프론트엔드인 경우: 웹 개발, 모바일 앱 개발 등)
*4대 보험 가입 여부*: (Y/N)
*MBTI*: (예: INTJ, ENFP 등)
*자기소개*: (자유롭게 작성해주세요)

💡 *작성 팁*
• 간결하고 명확하게 작성해주세요
• 자신의 강점과 경험을 포함해보세요
• 팀워크나 협업 경험이 있다면 언급해보세요
• 해커톤에서 하고 싶은 프로젝트가 있다면 간단히 소개해보세요

⚠️ *참고사항*
데이터베이스에 등록되지 않은 사용자입니다. 
웹 DB 뷰어(http://43.200.253.84:8081)에서 사용자 정보를 등록해주세요."""
        
        return {
            "response_type": "ephemeral",
            "text": template
        }