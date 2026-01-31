#!/bin/bash

set -e

################################
# Config
################################

git pull
git submodule update --init --recursive

IMAGE_NAME="autowatermark"
IMAGE_TAG="latest"
OUTPUT_FILE="${IMAGE_NAME}_${IMAGE_TAG}.tar"

################################
# Test
################################
echo "=== Step 1: Run tests ==="
if ! ./scripts/run_tests.sh; then
    echo "测试失败！"
    exit 1
fi

################################
# Build
################################
echo "=== Step 2: Build Docker Image ==="
if ! docker build --no-cache -t "${IMAGE_NAME}:${IMAGE_TAG}" .; then
    echo "构建失败！"
    exit 1
fi

################################
# Export
################################
echo "=== Step 3: Export and compress image ==="
if ! docker save -o "${OUTPUT_FILE}" "${IMAGE_NAME}:${IMAGE_TAG}"; then
    echo "导出失败！"
    exit 1
fi

################################
# Done
################################
echo "=== Complete ==="
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "Output: ${OUTPUT_FILE}"
