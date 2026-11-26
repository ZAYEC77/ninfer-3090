# ZAYEC77 NInfer fork

This repository keeps the native Codex fixes in C++: named app/peer context without an
assistant `call_id`, preserved source identity and app metadata, valid tool-result grouping,
and native opaque reasoning replay. External context remains user data and never acquires
system/developer authority. The public contract is in [serving.md](../docs/serving.md).

## Branches

- `master`: upstream development plus this fork's context patch and deployment tools.
- `release/codex-v0.18.0`: the qualified production baseline `v0.18.0-rtx3090` plus the
  context patch and reasoning-replay backport. Production uses this branch at an exact commit;
  unrelated newer model/kernel changes are not part of its build.

No credentials, private server configuration, user conversations, weights or binaries belong
in Git. Existing model files are reused. Heretic conversion and automatic model switching
are separate tasks; this deployment still serves the ordinary Qwen3.8-27B.

## Operate the server from one checkout

The server checkout is `/data/projects/ninfer` itself, tracking `release/codex-v0.18.0`.
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
git clone --branch release/codex-v0.18.0 https://github.com/ZAYEC77/ninfer-3090.git
cd ninfer-3090
revision=$(git rev-parse HEAD)
docker build -f deploy/Dockerfile --target protocol-tests -t ninfer-protocol-tests .
docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=none \
  -e NVIDIA_DRIVER_CAPABILITIES=compute,utility ninfer-protocol-tests
docker build -f deploy/Dockerfile --target runtime \
  --build-arg SOURCE_REVISION="$revision" -t "ninfer-local:$revision" .
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
