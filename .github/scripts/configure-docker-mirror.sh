#!/usr/bin/env bash
set -Eeuo pipefail

# Isolated GitHub Linux runners only. Production keeps its existing image defaults.
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_OS:-}" != "Linux" ]]; then
  echo "Docker mirror setup is restricted to GitHub Linux CI." >&2
  exit 2
fi
if [[ -n "$(docker ps --quiet)" ]]; then
  echo "Configure the CI mirror before starting any containers." >&2
  exit 2
fi

# Explicit immutable cache coordinates also work with containerd image stores,
# where daemon registry mirrors may fall back to a rate-limited Docker Hub.
# See https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images
postgres_ci_image='mirror.gcr.io/library/postgres@sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873'
redis_ci_image='mirror.gcr.io/library/redis@sha256:5f61955be8ab2ccee9372b84ae4d4da2e2b156f87281e3f218544055e7ee04d4'
docker pull "$postgres_ci_image"
docker tag "$postgres_ci_image" postgres:18-alpine
docker pull "$redis_ci_image"
docker tag "$redis_ci_image" redis:8.0-alpine

{
  echo 'XMAN_CI_PYTHON_IMAGE=mirror.gcr.io/library/python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f'
  echo 'XMAN_CI_NODE_IMAGE=mirror.gcr.io/library/node@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1'
  echo 'XMAN_CI_NGINX_IMAGE=mirror.gcr.io/library/nginx@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10'
  echo 'XMAN_CI_DOCKERFILE_IMAGE=mirror.gcr.io/docker/dockerfile@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e'
  echo 'XMAN_CI_BUILDKIT_IMAGE=mirror.gcr.io/moby/buildkit@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea'
} >> "${GITHUB_ENV:?GitHub CI environment file is required}"
