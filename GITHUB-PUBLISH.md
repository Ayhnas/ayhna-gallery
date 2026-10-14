# GitHub에서 NAS 이미지 호스팅

현재는 배포 구성만 준비되어 있습니다. 실제 GitHub 계정/저장소에 올리고 Actions가 성공해야 이미지 주소가 생깁니다.

1. GitHub 계정과 `ayhna-gallery` 저장소를 만듭니다.
2. 이 프로젝트의 `server/`, `deploy/`, `.github/workflows/publish-nas.yml`을 저장소 루트에 올립니다. `.env`나 실제 NAS 데이터는 올리지 않습니다.
3. Actions의 `Publish NAS image`가 실행됩니다. 서버 테스트가 통과한 뒤 Linux amd64/arm64 이미지를 GHCR에 게시합니다. GitHub가 발급하는 워크플로 토큰을 사용하므로 별도 Docker Hub 계정은 필요 없습니다.
4. 최초 게시 후 GitHub 계정의 Packages에서 `ayhna-gallery`의 접근 범위를 Public으로 변경합니다. 저장소가 공개여도 패키지가 자동으로 공개된다고 가정하면 안 됩니다.
5. 성공한 Actions 실행의 `AyhnaGallery-NAS-install` 아티팩트를 내려받습니다. 실제 게시 이미지의 digest가 들어간 `compose.yaml`입니다.
6. Compose의 `GALLERY_PAIR_SECRET` 빈 문자열에 원하는 연결 코드를 입력하고 NAS의 Compose 프로젝트로 실행합니다. 이 방식은 `.env`나 소스 폴더 없이 Compose 한 파일로 설치할 수 있습니다.

NAS 실행 명령:

```sh
docker compose up -d
```

클라이언트 연결 주소는 `http://NAS주소:8787`이고 연결 코드는 Compose에 입력한 값입니다.
업데이트할 때 새 빌드의 설치 Compose 파일로 이미지 digest를 갱신하면 됩니다. 저장 볼륨 이름과 프로젝트 이름을 유지하면 썸네일과 메타데이터를 유지합니다.

`.github`는 숨김 폴더이므로 업로드할 때 포함되어 있는지 확인합니다. 루트의 기존 `compose.yaml`은 로컬 소스 빌드용이고 Actions가 만들어 주는 Compose가 호스팅 이미지 설치용입니다.
