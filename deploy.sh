#!/bin/bash

# 배포 스크립트 (캐시 없이 완전 재배포, DB 데이터 보존)
set -e

echo "🚀 Starting deployment (no-cache rebuild, DB preserved)..."

# 프로젝트 디렉토리로 이동
cd /home/ubuntu/slack-bot/worunie-2025

# 최신 코드 가져오기
echo "📥 Pulling latest code from GitHub..."
git pull origin main

# DB 파일 존재 확인 및 백업
echo "🗄️ Checking database file..."
if [ -f "./teams.db" ]; then
    echo "✅ Database file found: teams.db"
    # 백업 생성 (안전을 위해)
    cp teams.db teams.db.backup.$(date +%Y%m%d_%H%M%S)
    echo "📋 Database backup created"
else
    echo "⚠️ Warning: teams.db not found!"
fi

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

# 기존 컨테이너 완전 중지 및 제거 (볼륨은 유지)
echo "🛑 Stopping and removing existing containers..."
docker-compose -f docker-compose.combined.yml down --remove-orphans || true

# 모든 관련 이미지 강제 제거
echo "🗑️ Removing all related images..."
docker images | grep "worunie-2025" | awk '{print $3}' | xargs -r docker rmi -f || true
docker images | grep "slack-bot" | awk '{print $3}' | xargs -r docker rmi -f || true
docker images | grep "db-viewer" | awk '{print $3}' | xargs -r docker rmi -f || true

# Docker 빌드 캐시 완전 정리
echo "🧹 Cleaning Docker build cache..."
docker builder prune -af --filter "until=24h" || true

# DB 파일 권한 확인 및 수정
echo "🔐 Setting database file permissions..."
chmod 644 teams.db 2>/dev/null || true
chown 1000:1000 teams.db 2>/dev/null || true

# 새로운 이미지 빌드 (캐시 없이)
echo "🔨 Building new images (no-cache)..."
docker-compose -f docker-compose.combined.yml build --no-cache --pull

# 컨테이너 시작
echo "🚀 Starting containers..."
docker-compose -f docker-compose.combined.yml up -d

# 배포 상태 확인
echo "✅ Checking deployment status..."
sleep 15

# 컨테이너 상태 확인
echo "📊 Container status:"
docker-compose -f docker-compose.combined.yml ps

# 로그 확인
echo "📋 Recent logs:"
docker-compose -f docker-compose.combined.yml logs --tail=20

# 이미지 정보 확인
echo "🖼️ Image information:"
docker images | grep -E "(worunie-2025|slack-bot|db-viewer)"

# DB 파일 상태 확인
echo "🗄️ Database file status:"
ls -la teams.db*
echo "📊 Database size: $(du -h teams.db | cut -f1)"

echo "🎉 Deployment completed successfully!"
echo "🌐 Slack Bot: http://$(curl -s ifconfig.me):8000"
echo "📊 DB Viewer: http://$(curl -s ifconfig.me):8081"
echo "💾 Database preserved: teams.db" 