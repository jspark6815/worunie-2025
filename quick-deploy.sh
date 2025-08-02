#!/bin/bash

echo "🚀 워런톤 슬랙 봇 빠른 배포 시작..."

# 시스템 업데이트
sudo apt-get update -y

# Docker 설치
sudo apt-get install -y docker.io docker-compose

# Docker 서비스 시작
sudo systemctl start docker
sudo systemctl enable docker

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER

# 애플리케이션 디렉토리 생성
mkdir -p ~/slack-bot
cd ~/slack-bot

# 프로젝트 파일 복사 (Git에서 가져오는 경우)
# git clone https://github.com/your-username/worunie-2025.git .

# 환경 변수 파일 생성
cat > .env << EOF
SLACK_SIGNING_SECRET=your_slack_signing_secret_here
SLACK_BOT_TOKEN=xoxb-your_bot_token_here
EOF

echo "✅ 배포 준비 완료!"
echo ""
echo "📝 다음 단계:"
echo "1. nano .env 명령어로 실제 슬랙 토큰을 입력하세요"
echo "2. docker-compose up -d 명령어로 애플리케이션을 시작하세요"
echo "3. 슬랙 앱 설정에서 Request URL을 http://$(curl -s ifconfig.me):8000으로 변경하세요"
echo ""
echo "🌐 EC2 공인 IP: $(curl -s ifconfig.me)" 