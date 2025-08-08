#!/bin/bash

# 배포 스크립트
set -e

echo "🚀 Starting deployment..."

# 프로젝트 디렉토리로 이동
cd /home/ubuntu/slack-bot/worunie-2025

# 최신 코드 가져오기
echo "📥 Pulling latest code from GitHub..."
git pull origin main

# 환경 변수 확인
if [ -z "$SLACK_SIGNING_SECRET" ] || [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "❌ Error: Required environment variables are not set"
    exit 1
fi

# 환경 변수 파일 생성
echo "📝 Creating .env file..."
cat > .env << EOF
SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET
SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN
EOF

# 기존 컨테이너 중지
echo "🛑 Stopping existing containers..."
docker-compose down || true
docker-compose -f docker-compose.db_viewer.yml down || true

# Docker 볼륨 생성 및 DB 파일 복사
echo "🗄️ Setting up database volume..."
docker volume create teams_db_data || true

# 기존 DB 파일이 있다면 볼륨에 복사
if [ -f "./teams.db" ]; then
    echo "📋 Copying existing database to volume..."
    docker run --rm -v teams_db_data:/data -v $(pwd):/backup alpine cp /backup/teams.db /data/teams.db || true
fi

# Docker 이미지 정리 (선택사항)
echo "🧹 Cleaning up old images..."
docker image prune -f || true

# 새로운 이미지 빌드 및 컨테이너 시작
echo "🔨 Building and starting Slack Bot..."
docker-compose up -d --build --force-recreate

echo "🔨 Building and starting DB Viewer..."
docker-compose -f docker-compose.db_viewer.yml up -d --build --force-recreate

# 배포 상태 확인
echo "✅ Checking deployment status..."
sleep 10

# 컨테이너 상태 확인
echo "📊 Container status:"
docker-compose ps
docker-compose -f docker-compose.db_viewer.yml ps

# 로그 확인
echo "📋 Recent logs:"
docker-compose logs --tail=10
docker-compose -f docker-compose.db_viewer.yml logs --tail=10

echo "🎉 Deployment completed successfully!"
echo "🌐 Slack Bot: http://$(curl -s ifconfig.me):8000"
echo "📊 DB Viewer: http://$(curl -s ifconfig.me):8081" 