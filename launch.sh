#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="flightmare"
DOCKERFILE_DIR="."

echo "==> Deteniendo contenedores de ${IMAGE_NAME}..."
docker ps -q --filter "ancestor=${IMAGE_NAME}" | xargs -r docker stop 2>/dev/null || true

echo "==> Eliminando imagen ${IMAGE_NAME}..."
docker rmi -f "${IMAGE_NAME}" 2>/dev/null || true

echo "==> Build desde cero (sin cache)..."
docker build --no-cache -t "${IMAGE_NAME}" "${DOCKERFILE_DIR}"

echo "==> Smoke test..."
docker run --rm "${IMAGE_NAME}" python3 -c "import flightgym; from rpg_baselines.common.policies import MlpPolicy; print('flightgym + rpg_baselines OK')"
docker run --rm "${IMAGE_NAME}" python3 -c "import ruamel.yaml; print('ruamel.yaml', ruamel.yaml.version_info)"

echo ""
echo "Listo. Entra al contenedor con:"
echo "  docker run -it --rm ${IMAGE_NAME} bash"
echo ""
echo "Prueba RL (headless, sin graficos):"
echo "  cd /home/flightmare/flightrl/examples"
echo "  export MPLBACKEND=Agg"
echo "  python3 run_drone_control.py --train 0 --render 0"
