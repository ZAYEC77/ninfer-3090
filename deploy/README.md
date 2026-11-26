# ZAYEC77 NInfer fork

This repository keeps the native Codex fixes in C++: named app/peer context without an
assistant `call_id`, preserved source identity and app metadata, valid tool-result grouping,
and native opaque reasoning replay. External context remains user data and never acquires
system/developer authority. The public contract is in [serving.md](../docs/serving.md).

## Production source

`master` integrates upstream `v0.20.0-rtx3090`, including the subsequent NVFP4 wide-prefill
fix, with this fork's native context patch and deployment tools. Each deployment records its
exact source commit and image ID. Upstream upgrades require the full qualification below;
`ninferctl update` follows this fork's `origin/master` and never merges upstream automatically.

No credentials, private server configuration, user conversations, weights or binaries belong
in Git. Existing model files are reused. Heretic conversion and automatic model switching
are separate tasks; this deployment still serves the ordinary Qwen3.8-27B.

## Operate the server from one checkout

The server checkout is `/data/projects/ninfer` itself, tracking `master`.
`origin` is this fork; operator settings live in ignored `.env`, and current deployment/test
records in ignored `.local/`. Neither is sent to Docker's build context. `models/` is a link
to the existing shared model directory; model files are not copied or removed.

```sh
cd /data/projects/ninfer
./ninferctl update     # git pull --ff-only, build, protocol tests, switch image, live checks
./ninferctl rebuild    # build the current local code and switch to it
./ninferctl restart    # restart the already built image
./ninferctl status
```

The operator needs the existing Docker/supervisor permissions, without sudo. Rebuild happens
while the current model keeps serving. The switch waits for active/queued requests, keeps the
GPU supervisor as the sole service owner, and restores the previous image in memory if the new
runtime fails verification. No backup files are created. `start` and `stop` are also available.
The private `.env` sets `NINFER_IMAGE`, `NINFER_CONTEXT` and `NINFER_BIND_ADDRESS` for the tracked
root `compose.yaml`. Supervisor's NInfer working directory must point at this checkout.
The default live check includes the existing user's Codex CLI; set `NINFER_VERIFY_CODEX=0` only
on installations without that client. Build concurrency defaults to four (`NINFER_BUILD_JOBS`).

`rebuild` accepts tracked local edits and labels them with a diff hash. For a published production
revision, commit and push the changes first. `update` follows the checkout's own tracking branch;
it does not automatically switch to upstream development.

## Build on a Linux Docker host

Check out an exact production commit before building. CUDA 12.8.1, Ubuntu 24.04 and SM86
are selected explicitly; no host compiler installation or GPU is required for compilation.
`BUILD_JOBS` defaults to four to bound memory use on the shared 30 GiB server. For a recorded
deployment, pass the resolved NVIDIA image digests via `CUDA_DEVEL_IMAGE` and
`CUDA_RUNTIME_IMAGE` and record the resulting image ID.

```sh
git clone --branch master https://github.com/ZAYEC77/ninfer-3090.git ninfer
cd ninfer
revision=$(git rev-parse HEAD)
docker build -f deploy/Dockerfile --target protocol-tests -t ninfer-protocol-tests .
docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=none \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility ninfer-protocol-tests
docker build -f deploy/Dockerfile --target runtime \
  --build-arg SOURCE_REVISION="$revision" \
  --build-arg SOURCE_VERSION="$(cat VERSION)" -t "ninfer-local:$revision" .
```

The four protocol suites cover OpenAI schema, Responses, Responses store and Anthropic schema.
This is not a full CUDA numerical or performance qualification. Retain the existing weights,
context limits, vision/speculation choices, port mappings and supervisor ownership when
changing the operator's production image. Update the operator's deployment lock to the source
commit and new image ID after live verification succeeds.

## Live checks

The native verifier uses only synthetic fixtures. It exercises app/peer context, actual image
input, canonical storage, token counting, continuation/fork replay, streamed reasoning replay,
real function/custom-tool round trips, malformed histories and existing Chat/Anthropic APIs.
It requires vision and tool support on the selected model.

```sh
python3 deploy/verify_native.py --base-url http://127.0.0.1:18082 --model qwen3.8-27b
python3 deploy/verify_codex.py
```

The Codex check uses the current user's existing CLI/provider configuration and verifies
shell -> apply_patch -> exact file content in a disposable directory. It does not reconfigure
Codex or alter existing chats. Application-injected context is also covered by the native
verifier; an actual desktop inter-chat check remains a separate client-level check.

## Compatibility boundaries

The fork supports the observed native Codex conversational protocol, not every hosted OpenAI
service. Hosted tools, Files/Conversations, audio and another provider's private reasoning
ciphertexts are outside this contract. NInfer's versioned reasoning token is an encoding,
not encryption or a signature. No quality or speed improvement is claimed by this patch.

## Full qualification before an upstream upgrade

Build the optional `qualification` target at a recorded source revision. It builds all standalone
CTest executables as well as the bundle, and uses Python 3.11 with pinned CPU PyTorch, NumPy,
Jinja2, pytest, safetensors and jsonschema for conversion and schema-oracle tests. The build tree
is inside the Docker checkout at `/src/build-linux`. These dependencies add nothing to the runtime image.

```sh
revision=$(git rev-parse HEAD)
docker build -f deploy/Dockerfile --target qualification \
  --build-arg SOURCE_REVISION="$revision" -t ninfer-qualification .
docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=none \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -v "$PWD/.git:/src/.git:ro" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/src \
  ninfer-qualification ctest -L cpu --parallel 4 --output-on-failure
docker run --rm -w /src ninfer-qualification /usr/local/bin/python3.11 -m pytest -q \
  tests/artifact tests/convert tests/flash_next tests/bench/ttft tests/test_serve_corpus.py tests/deploy
```

The read-only Git metadata is needed by the hermetic Vast launcher test (`git show HEAD:...`);
only the known `/src` checkout is marked safe for the container's different UID. Do not mount
operator settings or credentials. GPU-labelled tests require exclusive access to the card:
finish user requests, stop NInfer through its supervisor, mount the existing models read-only,
and supply the model only to compatible fixtures. The installed dense Qwen3.8 artifact lacks
MoE expert banks, DFlash v1 and a full Q8/FP8 output head; those real-model checks cannot be
qualified with this file. Run the two MoE numerical suites on their complete synthetic/FP64 inputs
without the artifact variable, and record their absent real-bank coverage separately.

```sh
other_profiles='^ninfer_(qwen3_5_(moe|dflash|dflash_prefill)_real|offloaded_moe_(layer|wide))_test$'
docker run --rm --gpus all --ulimit memlock=-1:-1 -e OMP_NUM_THREADS=12 \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -e NINFER_TEST_ARTIFACT=/models/qwen3_8_27b.ninfer \
  -v /data/shared/models/ninfer:/models:ro \
  ninfer-qualification ctest -L gpu --parallel 1 --output-on-failure -E "$other_profiles"
docker run --rm --gpus all --ulimit memlock=-1:-1 -e OMP_NUM_THREADS=12 \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility -e NINFER_TEST_ARTIFACT= \
  ninfer-qualification ctest -L gpu --parallel 1 --output-on-failure -R "$other_profiles"
docker run --rm --gpus all --ulimit memlock=-1:-1 \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  -v /data/shared/models/ninfer:/models:ro ninfer-qualification \
  /src/build-linux/tests/ninfer_tests ninfer_qwen3_5_loading_real_test \
  --artifact /models/qwen3_8_27b.ninfer --vision --speculative dflash2 --proposal optimized
```

The loading test needs its explicit `--artifact` argument; the generic environment variable does
not enable it. Always restore the previous service after qualification, including on test failure.
Record skips for absent model/graft/S3 prerequisites separately from passed tests. Do not reduce
numerical tolerances or treat a missing model prerequisite as a passed real-model check.
