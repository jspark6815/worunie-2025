import os
import hmac
import hashlib
import json
import requests
import logging
import urllib.parse
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.orm import Session
from .models import get_db, TEAM_COMPOSITION
from .team_service import TeamBuildingService
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

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
    
    team_service = TeamBuildingService(db)
    
    if command == '/팀생성':
        return handle_create_team(text, user_id, user_name, team_service)
    elif command == '/팀빌딩':
        return handle_add_member(text, user_id, user_name, team_service)
    elif command == '/팀정보':
        return handle_team_info(text, team_service)
    elif command == '/팀목록':
        return handle_team_list(team_service)
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
    
    result = team_service.create_team(text, user_id, user_name)
    
    if result["success"]:
        return {
            "response_type": "in_channel",
            "text": f"🎉 {result['message']}\n팀장: <@{user_id}>"
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        }

def handle_add_member(text: str, user_id: str, user_name: str, team_service: TeamBuildingService):
    """팀 멤버 추가 처리"""
    if not text:
        help_text = "사용법: `/팀빌딩 포지션 @유저명`\n"
        help_text += "예시: `/팀빌딩 BE @john`\n"
        help_text += "가능한 포지션:\n"
        for position, count in TEAM_COMPOSITION.items():
            help_text += f"• {position}: {count}명\n"
        return {
            "response_type": "ephemeral",
            "text": help_text
        }
    
    # 텍스트 파싱: "BE @john" -> position="BE", target_user="@john"
    parts = text.split()
    if len(parts) != 2:
        return {
            "response_type": "ephemeral",
            "text": "사용법: `/팀빌딩 포지션 @유저명`\n예시: `/팀빌딩 BE @john`"
        }
    
    position, target_user = parts
    
    # @제거하고 user_id 추출
    if not target_user.startswith('@'):
        return {
            "response_type": "ephemeral",
            "text": "유저명은 @로 시작해야 합니다.\n예시: `/팀빌딩 BE @john`"
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
            "response_type": "in_channel",
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
        response_text = f"📋 **{result['team_name']}** 팀 정보\n"
        response_text += f"생성일: {result['created_at']}\n\n"
        
        response_text += "👥 **팀 구성 현황**\n"
        for position, status in result["status"].items():
            emoji = "✅" if status["filled"] else "❌"
            response_text += f"{emoji} {position}: {status['current']}/{status['required']}명\n"
        
        if result["members"]:
            response_text += "\n**팀 멤버**\n"
            response_text += "\n".join(result["members"])
        else:
            response_text += "\n**팀 멤버**: 아직 없음"
        
        return {
            "response_type": "in_channel",
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
                "response_type": "in_channel",
                "text": "📋 **팀 목록**\n아직 생성된 팀이 없습니다.\n`/팀생성 팀명`으로 팀을 만들어보세요!"
            }
        
        response_text = "📋 **팀 목록**\n"
        for team in result["teams"]:
            status_emoji = "✅" if team["is_complete"] else "⏳"
            response_text += f"{status_emoji} **{team['name']}** ({team['member_count']}/{team['total_required']}명)\n"
            response_text += f"   생성일: {team['created_at']}\n\n"
        
        return {
            "response_type": "in_channel",
            "text": response_text
        }
    else:
        return {
            "response_type": "ephemeral",
            "text": f"❌ {result['message']}"
        } 