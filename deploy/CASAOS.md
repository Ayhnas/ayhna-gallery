# CasaOS 설치 · AyhnaGallery NAS v0.2.0

[CasaOS용 Compose 다운로드](https://raw.githubusercontent.com/Ayhnas/ayhna-gallery/main/deploy/compose-casaos.yaml)

NAS 터미널에서 데이터 폴더를 한 번 준비한 뒤, CasaOS의 사용자 지정 설치에서 Compose 파일을 가져옵니다.

```sh
sudo mkdir -p /DATA/AppData/ayhna-gallery
sudo chown 10001:10001 /DATA/AppData/ayhna-gallery
```

폴더 안에는 썸네일·메타데이터·서버 설정만 저장됩니다. 기존 설치가 있다면 현재 데이터 경로를 그대로 유지해서 업데이트하세요. 새 경로는 기존 Docker 볼륨 데이터를 자동으로 옮기지 않습니다.

수동 설치 화면 입력값:

| 항목 | 값 |
|---|---|
| Docker 이미지 | `ghcr.io/ayhnas/ayhna-gallery` |
| Tag | `0.2.0` |
| 제목 | `AyhnaGallery` |
| Web UI | `http://192.168.1.88:8787/` |
| 네트워크 | `bridge` |
| 포트 | 호스트 `8787` → 컨테이너 `8787`, `TCP` |
| 볼륨 | 호스트 `/DATA/AppData/ayhna-gallery` → 컨테이너 `/data` |
| 환경 변수 | 추가할 필요 없음 |
| 컨테이너 명령어 | 비워 둠: 이미지 기본 명령 사용 |
| 권한(Privileged) | 끔 |
| 재시작 정책 | `unless-stopped` |

아이콘 URL:

```text
https://raw.githubusercontent.com/Ayhnas/ayhna-gallery/main/assets/icon.svg
```

Docker 명령으로 설치할 경우 Compose 설치 대신 다음을 사용합니다.

```sh
sudo mkdir -p /DATA/AppData/ayhna-gallery
sudo chown 10001:10001 /DATA/AppData/ayhna-gallery
sudo docker run -d \
  --name ayhna-gallery \
  --restart unless-stopped \
  --user 10001:10001 \
  --network bridge \
  -p 8787:8787/tcp \
  --mount type=bind,source=/DATA/AppData/ayhna-gallery,target=/data \
  --label icon=https://raw.githubusercontent.com/Ayhnas/ayhna-gallery/main/assets/icon.svg \
  ghcr.io/ayhnas/ayhna-gallery:0.2.0
```

설치 후 웹 화면에서 서버 이름과 연결 비밀번호를 정합니다. PC와 Android 앱에서도 `http://192.168.1.88:8787` 및 같은 비밀번호를 사용합니다.

Compose의 제목·아이콘·포트·Web UI 설정은 [CasaOS 공식 Compose 예시](https://github.com/IceWhaleTech/CasaOS-AppStore/blob/main/Apps/ESPHome/docker-compose.yml)의 `x-casaos` 구조를 따릅니다. 설치 대상 CasaOS에서의 실제 가져오기/설치는 별도로 진행해야 합니다.
