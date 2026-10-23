import asyncio
import os
import sys
import tempfile
import requests
from config import ConfigManager
from wordpress import WordPressPublisher

SAMPLE_GPX_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="RealTestRunner" xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Real Test Track</name>
    <trkseg>
      <trkpt lat="37.3500" lon="126.9300">
        <ele>50.0</ele>
        <time>2026-04-18T10:00:00Z</time>
      </trkpt>
      <trkpt lat="37.3510" lon="126.9310">
        <ele>52.0</ele>
        <time>2026-04-18T10:05:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
"""


async def run_diagnostics():
    print("=" * 60)
    print(" [1/5] 환경설정 및 워드프레스 연결 정보 확인")
    print("=" * 60)
    config = ConfigManager()

    print(f"- WORDPRESS_URL: {config.WORDPRESS_URL}")
    print(f"- WORDPRESS_USERNAME: {config.WORDPRESS_USERNAME}")
    print(f"- WORDPRESS_PASSWORD 설정 여부: {'예 (설정됨)' if config.WORDPRESS_PASSWORD else '아니오 (누락)'}")

    publisher = WordPressPublisher(config)
    if not publisher.is_enabled:
        print("\n❌ 실패: 워드프레스 인증 정보가 누락되어 있습니다. .env 파일을 확인해 주세요.")
        return False

    auth = publisher._get_auth_headers()

    print("\n" + "=" * 60)
    print(" [2/5] REST API 인증 및 사용자 권한 확인")
    print("=" * 60)
    user_url = f"{publisher.base_url.rstrip('/')}/wp-json/wp/v2/users/me"
    try:
        res = requests.get(user_url, auth=auth, timeout=15)
        print(f"- GET {user_url} -> Status Code: {res.status_code}")
        if res.status_code == 200:
            user_data = res.json()
            print(f"- 인증된 사용자: {user_data.get('name')} (ID: {user_data.get('id')})")
        else:
            print(f"❌ 인증 실패: 응답 본문 -> {res.text}")
            return False
    except Exception as e:
        print(f"❌ 연결 오류: {e}")
        return False

    print("\n" + "=" * 60)
    print(" [3/5] 지정 카테고리(1792) 존재 여부 확인")
    print("=" * 60)
    category_url = f"{publisher.base_url.rstrip('/')}/wp-json/wp/v2/categories/1792"
    try:
        cat_res = requests.get(category_url, auth=auth, timeout=10)
        if cat_res.status_code == 200:
            cat_data = cat_res.json()
            print(f"✓ 카테고리 1792 확인 완료: '{cat_data.get('name')}'")
        else:
            print(f"⚠️ 경고: 카테고리 ID 1792 가 존재하지 않습니다 (Status {cat_res.status_code}).")
            print("   워드프레스 설정에 따라 존재하지 않는 카테고리 지정 시 포스팅이 거절될 수 있습니다.")
    except Exception as e:
        print(f"⚠️ 카테고리 확인 중 오류: {e}")

    print("\n" + "=" * 60)
    print(" [4/5] 실제 GPX 미디어 파일 업로드 테스트")
    print("=" * 60)
    with tempfile.NamedTemporaryFile("w", suffix=".gpx", delete=False) as f:
        f.write(SAMPLE_GPX_CONTENT)
        temp_gpx_path = f.name

    try:
        media_id, media_url, source_url = await publisher.upload_media(temp_gpx_path)
        if media_id:
            print(f"✓ GPX 업로드 성공! Media ID: {media_id}")
            print(f"  URL: {media_url}")
        else:
            print("⚠️ GPX 미디어 업로드 실패 (워드프레스에서 GPX 확장자를 차단했거나 권한 부족)")
            print("   (미디어 업로드가 실패해도 글 포스팅 자체는 가능한지 계속 테스트합니다.)")
    finally:
        if os.path.exists(temp_gpx_path):
            os.remove(temp_gpx_path)

    print("\n" + "=" * 60)
    print(" [5/5] 워드프레스 실제 글(Post) 등록 테스트")
    print("=" * 60)
    test_title = "[테스트] GPX 연동 확인 포스트"
    test_content = (
        "<h2>테스트 포스팅입니다.</h2>"
        "<p>GPX 봇과 워드프레스 연동 정상 동작 여부를 확인 중입니다.</p>"
        '<p>[sgpx gpx="/wp-content/uploads/gpx/sample_test.gpx"]</p>'
    )

    created_post = publisher.create_post(
        title=test_title,
        content=test_content,
        status="draft",
        featured_media_id=None
    )

    if created_post and created_post.get("id"):
        post_id = created_post["id"]
        post_link = created_post.get("link", "N/A")
        print("✓ 실제 포스팅 성공!")
        print(f"- 생성된 글 ID: {post_id}")
        print(f"- 글 확인 링크: {post_link}")
        print("\n🎉 모든 실 연동 테스트를 통과했습니다.")
        return True
    else:
        print("❌ 포스팅 생성 실패. 워드프레스 응답 로그를 확인해 주세요.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_diagnostics())
    sys.exit(0 if success else 1)
