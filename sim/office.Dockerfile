# 발표 자료 확인용 — pptx → pdf → 쪽마다 png (LibreOffice Impress, 한글 Noto CJK)
#   ./tools.sh report-check   (이미지 이름 snss/office)
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress fonts-noto-cjk poppler-utils \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /w
