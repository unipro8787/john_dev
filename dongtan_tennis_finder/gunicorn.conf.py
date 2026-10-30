# gunicorn이 실행 폴더에서 자동으로 읽는 설정 파일.
# Render는 Procfile이 아니라 대시보드의 Start Command(gunicorn app:app)로 실행하므로 설정은 여기에 둔다.

# 남동구 첫 조회처럼 오래 걸리는 요청(Render에서 17초쯤)이 있어도 다른 방문자 요청을 바로 처리하도록
# 워커 하나에 스레드 8개를 둔다 (gthread 워커). 앱의 캐시·세션은 스레드에 안전하게 짜여 있다.
threads = 8
