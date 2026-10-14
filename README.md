# AyhnaGallery NAS · v0.2.0

PC와 Android의 공유 앨범을 연결하는 개인 NAS 서버입니다. 썸네일·메타데이터를 보관하고 원본은 요청할 때 기기에서 중계합니다.

## 설치

```sh
docker run -d \
  --name ayhna-gallery \
  --restart unless-stopped \
  -p 8787:8787 \
  -v ayhna-gallery-data:/data \
  ghcr.io/ayhnas/ayhna-gallery:0.2.0
```

1. 브라우저에서 `http://NAS주소:8787`을 엽니다.
2. 초기 설정 화면에서 서버 이름과 서버 연결 비밀번호를 정합니다.
3. AyhnaCam의 NAS 갤러리 또는 Android 앱의 설정에서 NAS 주소와 같은 비밀번호로 기기를 등록합니다.

명령에 비밀번호를 넣거나 `.env` 파일을 편집할 필요가 없습니다. 설정과 등록 정보는 Docker 볼륨에 유지됩니다.

관리 화면에서 기기 연결 상태, 사진 수, 썸네일 용량을 확인하고 서버 이름·비밀번호·기기 이름을 변경하거나 기기 등록을 해제할 수 있습니다. 등록 해제는 원본 사진 파일을 삭제하지 않습니다.

## Compose

[설치용 compose.yaml](https://raw.githubusercontent.com/Ayhnas/ayhna-gallery/main/deploy/compose.yaml)을 NAS 프로젝트에 넣고 `docker compose up -d`로 실행할 수 있습니다. 실행 후 같은 웹 화면에서 초기 설정합니다.

## 기존 버전에서 업데이트

기존 `ayhna-gallery-data` 볼륨을 유지한 채 컨테이너만 새 이미지로 교체합니다. 컨테이너 삭제 시 볼륨 삭제 옵션을 사용하지 않습니다.

```sh
docker stop ayhna-gallery
docker rm ayhna-gallery
```

그다음 위의 v0.2.0 설치 명령을 실행합니다. 이전 버전에서 환경 변수로만 비밀번호를 정했다면 새 웹 화면에서 비밀번호를 다시 설정합니다. 기존 기기 등록은 유지됩니다. 저장된 비밀번호가 있거나 기존 비밀번호 환경 변수를 유지한 경우에는 로그인 화면이 나타납니다.

## 개발과 검증

서버: Python / FastAPI / SQLite. 웹 설정 UI는 외부 CDN 없이 컨테이너에 포함됩니다.

GitHub Actions는 서버·관리 API 통합 검사를 실행한 뒤 Linux amd64/arm64 이미지를 게시하고, 실제 두 아키텍처 컨테이너에서 초기 설정·로그인·기기 등록을 검사합니다.

```sh
python -m pip install -r server/requirements.txt
python server/test_server.py
python server/test_admin.py
```

개인 공유 그룹용이며 등록된 기기끼리 사진 목록을 공유합니다. Android 앱이 OS 정책으로 중단되면 원본 요청은 대기하며 앱을 다시 실행해야 합니다.
