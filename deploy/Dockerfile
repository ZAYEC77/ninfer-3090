# syntax=docker/dockerfile:1
# Keep the serving-only production branch on the qualified CUDA 12.8 / SM86 route.
ARG CUDA_DEVEL_IMAGE=nvidia/cuda:12.8.1-devel-ubuntu24.04
ARG CUDA_RUNTIME_IMAGE=nvidia/cuda:12.8.1-runtime-ubuntu24.04
FROM ${CUDA_DEVEL_IMAGE} AS build
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates cmake ninja-build pkg-config ccache python3 \
    libavcodec-dev libavformat-dev libavutil-dev libswscale-dev \
    libcurl4-openssl-dev libzstd-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . .
# Four jobs keep this build usable on the shared 30 GiB operator host.
ARG BUILD_JOBS=4
RUN --mount=type=cache,id=ninfer-codex-ccache,target=/root/.cache/ccache \
    cmake -S . -B /build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CUDA_ARCHITECTURES=86 -DNINFER_BUILD_APPS=ON \
      -DBUILD_TESTING=ON -DNINFER_BUILD_BENCHMARKS=OFF \
    && cmake --build /build --parallel ${BUILD_JOBS} --target ninfer ninfer-serve ninfer_tests

# Protocol tests need the host driver's libcuda but no GPU device. Run the build stage with
# --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=none -e NVIDIA_DRIVER_CAPABILITIES=compute,utility.
FROM build AS protocol-tests
WORKDIR /build
CMD ["ctest", "--output-on-failure", "-R", "^ninfer_(openai_schema|openai_responses|openai_responses_store|anthropic_schema)_test$"]

FROM ${CUDA_RUNTIME_IMAGE} AS runtime
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libavcodec60 libavformat60 libavutil58 libswscale7 libcurl4t64 libzstd1 \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /usr/local/cuda-12.8/compat /usr/local/cuda/compat
COPY --from=build /build/apps/ninfer /opt/ninfer/ninfer
COPY --from=build /build/apps/ninfer-serve /opt/ninfer/ninfer-serve
ENV PATH="/opt/ninfer:${PATH}"
ARG SOURCE_REVISION
LABEL org.opencontainers.image.source="https://github.com/ZAYEC77/ninfer-3090" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.version="0.18.0-codex.1"
WORKDIR /workspace
EXPOSE 8080
STOPSIGNAL SIGTERM
CMD ["ninfer-serve", "--help"]
