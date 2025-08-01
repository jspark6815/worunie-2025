import os
import hmac
import hashlib
import json
import requests
import logging
from fastapi import APIRouter, Request, Header, HTTPException
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

router = APIRouter()
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

def verify_slack_request(body: bytes, signature: str, timestamp: str):
    """Slack 요청 서명 검증"""
    # 환경 변수가 없으면 검증을 건너뛰기 (개발용)
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

@router.post("/events")
async def handle_events(
    request: Request,
    x_slack_signature: str = Header(...),
    x_slack_request_timestamp: str = Header(...)
):
    body = await request.body()
    verify_slack_request(body, x_slack_signature, x_slack_request_timestamp)
    payload = json.loads(body)
    
    logger.info(f"Received event: {payload.get('type', 'unknown')}")

    # 슬랙 URL 검증용 응답
    if payload.get("type") == "url_verification":
        logger.info("URL verification request received")
        return {"challenge": payload.get("challenge")}

    # 신규 팀원 입장 이벤트 처리
    event = payload.get("event", {})
    logger.info(f"Event type: {event.get('type', 'unknown')}")
    
    if event.get("type") == "team_join":
        user_id = event["user"]["id"]
        logger.info(f"Team join event for user: {user_id}")
        send_welcome_dm(user_id)
    
    # 채널 입장 이벤트 처리
    elif event.get("type") == "member_joined_channel":
        user_id = event["user"]
        channel_id = event["channel"]
        logger.info(f"Member joined channel: user={user_id}, channel={channel_id}")
        send_channel_welcome_message(user_id, channel_id)

    return {"ok": True}

def send_welcome_dm(user_id: str):
    """DM 채널을 열고 환영 메시지 전송"""
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    # 1) DM 채널 오픈
    open_resp = requests.post(
        "https://slack.com/api/conversations.open",
        json={"users": user_id},
        headers=headers
    )
    channel_id = open_resp.json()["channel"]["id"]

    # 2) 메시지 전송
    welcome_text = (
        f"🎉 워런톤에 오신 걸 환영합니다, <@{user_id}>님!\n\n"
        "🔔 필수 채널 안내\n"
        "• #공지사항\n"
        "• #가이드\n"
        "• #자기소개 작성\n"
        "• 팀 빌딩은 `/팀빌딩` 명령어를 사용하세요!\n\n"
        "즐거운 해커톤 되세요! 🚀"
    )
    requests.post(
        "https://slack.com/api/chat.postMessage",
        json={"channel": channel_id, "text": welcome_text},
        headers=headers
    )

def send_channel_welcome_message(user_id: str, channel_id: str):
    """채널별 입장 안내 메시지 전송"""
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # 채널 정보 가져오기
    channel_info_resp = requests.get(
        f"https://slack.com/api/conversations.info",
        params={"channel": channel_id},
        headers=headers
    )
    
    if channel_info_resp.status_code != 200:
        return
    
    channel_info = channel_info_resp.json()
    if not channel_info.get("ok"):
        return
    
    channel_name = channel_info["channel"]["name"]
    
    # 채널별 안내 메시지 설정
    channel_messages = {
        "announcement": (
            f"👋 <@{user_id}>님이 #announcement 채널에 입장하셨습니다!\n\n"
            "📢 이 채널에서는 해커톤의 중요한 공지사항을 확인할 수 있습니다.\n"
            "• 해커톤 일정 및 규칙\n"
            "• 기술 세션 안내\n"
            "• 시상식 정보\n"
            "• 긴급 공지사항\n\n"
            "꼭 확인해주세요! 🔔"
        ),
        "guide": (
            f"👋 <@{user_id}>님이 #guide 채널에 입장하셨습니다!\n\n"
            "📚 이 채널에서는 해커톤 참여 가이드를 확인할 수 있습니다.\n"
            "• 개발 환경 설정\n"
            "• API 사용법\n"
            "• 기술 스택 가이드\n"
            "• 질문과 답변\n\n"
            "궁금한 점이 있으면 언제든 물어보세요! 💡"
        ),
        "self-introduce": (
            f"👋 <@{user_id}>님이 #self-introduce 채널에 입장하셨습니다!\n\n"
            "🤝 이 채널에서는 팀원들과 서로를 알아갈 수 있습니다.\n"
            "• 본인의 기술 스택과 관심 분야를 소개해주세요\n"
            "• 팀 빌딩에 도움이 됩니다\n"
            "• 자기소개 템플릿을 참고하세요\n\n"
            "즐거운 팀 빌딩 되세요! 🚀"
        ),
        "team-building": (
            f"👋 <@{user_id}>님이 #team-building 채널에 입장하셨습니다!\n\n"
            "👥 이 채널에서는 팀을 구성할 수 있습니다.\n"
            "• 팀원 모집 및 합류\n"
            "• 프로젝트 아이디어 공유\n"
            "• 팀 소개 및 홍보\n"
            "• 협업 도구 안내\n\n"
            "멋진 팀을 만들어보세요! 💪"
        ),
        "qna": (
            f"👋 <@{user_id}>님이 #qna 채널에 입장하셨습니다!\n\n"
            "❓ 이 채널에서는 질문과 답변을 나눌 수 있습니다.\n"
            "• 기술 관련 질문\n"
            "• 해커톤 규칙 문의\n"
            "• 개발 환경 문제 해결\n"
            "• 멘토링 요청\n\n"
            "편하게 질문해주세요! 🤔"
        ),
        "fun-free-talk": (
            f"👋 <@{user_id}>님이 #fun-free-talk 채널에 입장하셨습니다!\n\n"
            "💬 이 채널에서는 자유롭게 대화할 수 있습니다.\n"
            "• 일상적인 대화\n"
            "• 기술 관련 토론\n"
            "• 해커톤 이야기\n"
            "• 휴식 시간\n\n"
            "즐거운 대화 되세요! 😊"
        )
    }
    
    # 채널명에 따른 메시지 선택
    welcome_message = channel_messages.get(channel_name, 
        f"👋 <@{user_id}>님이 #{channel_name} 채널에 입장하셨습니다!\n\n"
        f"이 채널에서 다양한 이야기를 나누어보세요! 💬"
    )
    
    # 메시지 전송
    requests.post(
        "https://slack.com/api/chat.postMessage",
        json={
            "channel": channel_id, 
            "text": welcome_message,
            "unfurl_links": False,
            "unfurl_media": False
        },
        headers=headers
    )
