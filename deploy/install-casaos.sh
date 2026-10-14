#!/bin/sh
set -eu
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
