import os
import hmac
import hashlib
import json
import requests
from fastapi import APIRouter, Request, Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

def verify_slack_request(body: bytes, signature: str, timestamp: str):
    """Slack 요청 서명 검증"""
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

    # 슬랙 URL 검증용 응답
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # 신규 팀원 입장 이벤트 처리
    event = payload.get("event", {})
    if event.get("type") == "team_join":
        user_id = event["user"]["id"]
        send_welcome_dm(user_id)

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
