#!/bin/bash

# EC2 배포 스크립트

echo "🚀 워런톤 슬랙 봇 배포 시작..."

# 시스템 업데이트
echo "📦 시스템 패키지 업데이트..."
sudo apt-get update
sudo apt-get upgrade -y

# Docker 설치
echo "🐳 Docker 설치..."
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

# Docker Compose 설치
echo "📋 Docker Compose 설치..."
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Docker 서비스 시작
echo "🔧 Docker 서비스 시작..."
sudo systemctl start docker
sudo systemctl enable docker

# 현재 사용자를 docker 그룹에 추가
sudo usermod -aG docker $USER

# 애플리케이션 디렉토리 생성
echo "📁 애플리케이션 디렉토리 설정..."
mkdir -p /home/ubuntu/slack-bot
cd /home/ubuntu/slack-bot

# 환경 변수 파일 생성 (실제 값으로 수정 필요)
echo "🔐 환경 변수 파일 생성..."
cat > .env << EOF
SLACK_SIGNING_SECRET=your_slack_signing_secret_here
SLACK_BOT_TOKEN=xoxb-your_bot_token_here
EOF

echo "✅ 배포 준비 완료!"
echo "📝 다음 단계:"
echo "1. .env 파일에 실제 슬랙 토큰을 입력하세요"
echo "2. docker-compose up -d 명령어로 애플리케이션을 시작하세요"
echo "3. 슬랙 앱 설정에서 Request URL을 EC2 IP:8000으로 변경하세요" 