"""Produce a source-free NAS Compose file after a container image is actually published."""
import argparse
import json
import re
from pathlib import Path

def render(image):
    if not re.fullmatch(r'ghcr\.io/[a-z0-9][a-z0-9_.-]*/ayhna-gallery@sha256:[a-f0-9]{64}',image):
        raise ValueError('A published GHCR image digest is required.')
    return f'''services:
  gallery:
    image: {json.dumps(image)}
    ports:
      - "8787:8787"
    environment:
      # Set your own pairing code here before starting the project.
      GALLERY_PAIR_SECRET: ""
    volumes:
      - gallery-data:/data
    restart: unless-stopped
volumes:
  gallery-data:
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('image');parser.add_argument('--output',default='compose.yaml')
    args=parser.parse_args();output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(render(args.image),encoding='utf-8')
