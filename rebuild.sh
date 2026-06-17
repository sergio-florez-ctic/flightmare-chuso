#!/bin/bash
# Script para aplicar los cambios C++ Y recompilar dentro del Docker
set -e

echo "=== Aplicando cambios al codigo C++ ==="

FLIGHTLIB="/home/flightmare/flightlib"

# ---------------------------------------------------------------
# 1. Cambiar world_box de z=-100 a z=-200 en quadrotor_env.cpp
# ---------------------------------------------------------------
echo "[1/6] Expandiendo world_box a z=-200..."
sed -i 's/world_box_ << -20000, 20000, -20000, 20000, -100, 20000;/world_box_ << -20000, 20000, -20000, 20000, -200, 20000;/' \
  "$FLIGHTLIB/src/envs/quadrotor_env/quadrotor_env.cpp"

# Verificar
grep "world_box_" "$FLIGHTLIB/src/envs/quadrotor_env/quadrotor_env.cpp" | head -1
echo "  -> OK"

# ---------------------------------------------------------------
# 2. Anadir bloque else con quaternion identidad y z=-10 en reset()
# ---------------------------------------------------------------
echo "[2/6] Anadiendo reset determinista (quaternion identidad, z=-10)..."

# Reemplazar la linea "  }" que cierra el if(random) con el bloque else completo
# Buscamos el patron exacto: "    quad_state_.qx /= quad_state_.qx.norm();\n  }"
# y lo reemplazamos por el bloque con else

python3 -c "
import re

filepath = '$FLIGHTLIB/src/envs/quadrotor_env/quadrotor_env.cpp'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Patron: cierre del if(random) - despues de la normalizacion del quaternion
old = '''    quad_state_.qx /= quad_state_.qx.norm();
  }
  // reset quadrotor with random states'''

new = '''    quad_state_.qx /= quad_state_.qx.norm();
  } else {
    // Deterministic reset: upright at origin, 10m altitude
    // Identity quaternion (w=1, x=0, y=0, z=0) = no rotation
    quad_state_.x(QS::ATTW) = 1.0;
    quad_state_.x(QS::ATTX) = 0.0;
    quad_state_.x(QS::ATTY) = 0.0;
    quad_state_.x(QS::ATTZ) = 0.0;
    // Start at 10m altitude (NED: z=-10)
    quad_state_.x(QS::POSZ) = -10.0;
  }
  // reset quadrotor with deterministic state'''

if old in content:
    content = content.replace(old, new)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('  -> OK: bloque else anadido')
elif 'Deterministic reset' in content:
    print('  -> Ya aplicado previamente, saltando')
else:
    print('  -> ERROR: no se encontro el patron esperado')
    print('  Contenido del reset:')
    # Print lines around qx /= to debug
    for i, line in enumerate(content.split('\n')):
        if 'qx /=' in line or 'reset quadrotor' in line:
            print(f'    L{i}: {line}')
    exit(1)
"

# ---------------------------------------------------------------
# 3. Cambiar default de random=true a random=false en headers
# ---------------------------------------------------------------
echo "[3/6] Cambiando default random=true a random=false..."

sed -i 's/bool reset(Ref<Vector<>> obs, const bool random = true)/bool reset(Ref<Vector<>> obs, const bool random = false)/' \
  "$FLIGHTLIB/include/flightlib/envs/quadrotor_env/quadrotor_env.hpp"

sed -i 's/virtual bool reset(Ref<Vector<>> obs, const bool random = true)/virtual bool reset(Ref<Vector<>> obs, const bool random = false)/' \
  "$FLIGHTLIB/include/flightlib/envs/env_base.hpp"

# Verificar
echo -n "  quadrotor_env.hpp: "
grep "bool reset" "$FLIGHTLIB/include/flightlib/envs/quadrotor_env/quadrotor_env.hpp"
echo -n "  env_base.hpp:      "
grep "virtual bool reset" "$FLIGHTLIB/include/flightlib/envs/env_base.hpp"

# ---------------------------------------------------------------
# 4. Pinear pybind11 a v2.10.4
# ---------------------------------------------------------------
echo "[4/6] Pineando pybind11 a v2.10.4..."
sed -i 's/GIT_TAG           master/GIT_TAG           v2.10.4/' \
  "$FLIGHTLIB/cmake/pybind11_download.cmake"
grep "GIT_TAG" "$FLIGHTLIB/cmake/pybind11_download.cmake"
echo "  -> OK"

# ---------------------------------------------------------------
# 5. Limpiar y recompilar
# ---------------------------------------------------------------
echo ""
echo "[5/6] Recompilando..."
BUILD_DIR="$FLIGHTLIB/build"
rm -rf "$BUILD_DIR"/*
rm -rf "$FLIGHTLIB/externals/pybind11-src"
rm -rf "$FLIGHTLIB/externals/pybind11-bin"
rm -rf "$FLIGHTLIB/externals/pybind11-download"

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake "$FLIGHTLIB" \
  -DCMAKE_BUILD_TYPE=Release \
  -DPYTHON_EXECUTABLE=/usr/bin/python3 \
  -DBUILD_TESTS=OFF \
  -DBUILD_UNITY_BRIDGE_TESTS=OFF \
  2>&1 | tail -5

echo "Compilando..."
make -j$(nproc) 2>&1 | tail -5

# ---------------------------------------------------------------
# 6. Instalar el .so compilado
# ---------------------------------------------------------------
echo ""
echo "[6/6] Instalando .so..."

SO_FILE=$(find "$BUILD_DIR" -name "flightgym*.so" -type f 2>/dev/null | head -1)
if [ -z "$SO_FILE" ]; then
  echo "ERROR: No se encontro flightgym*.so"
  exit 1
fi
echo "  Compilado: $SO_FILE"

# Buscar TODAS las copias del .so y reemplazarlas
echo "  Buscando copias existentes del .so..."
find / -name "flightgym*.so" -type f 2>/dev/null | while read existing; do
  if [ "$existing" != "$SO_FILE" ]; then
    echo "  Reemplazando: $existing"
    cp -f "$SO_FILE" "$existing"
  fi
done

# Verificar
echo ""
echo "=== Verificando ==="
cd /tmp
python3 -c "
from ruamel.yaml import YAML, dump, RoundTripDumper
from flightgym import QuadrotorEnv_v1
from rpg_baselines.envs import vec_env_wrapper as wrapper
import numpy as np
import os

cfg_path = os.path.join(os.environ['FLIGHTMARE_PATH'], 'flightlib', 'configs', 'vec_env.yaml')
cfg = YAML().load(open(cfg_path, 'r'))
cfg['env']['seed'] = 42
cfg['env']['scene_id'] = 0
cfg['env']['num_envs'] = 1
cfg['env']['num_threads'] = 1
cfg['env']['render'] = 'no'

env = wrapper.FlightEnvVec(QuadrotorEnv_v1(dump(cfg, Dumper=RoundTripDumper), False))
obs = env.reset()
state = obs[0]
print(f'Posicion inicial: x={state[0]:.2f}, y={state[1]:.2f}, z={state[2]:.2f}')
print(f'Actitud:          roll={np.degrees(state[3]):.1f}, pitch={np.degrees(state[4]):.1f}, yaw={np.degrees(state[5]):.1f}')

if abs(state[2] - (-10.0)) < 1.0 and abs(state[3]) < 0.1 and abs(state[4]) < 0.1:
    print('EXITO: El dron empieza a 10m de altura, orientado correctamente!')
else:
    print('FALLO: El reset sigue siendo aleatorio. Los cambios NO se aplicaron.')
    print('  Se esperaba: z=-10.0, roll=0, pitch=0')
"

echo ""
echo "=== Ahora ejecuta: ==="
echo "  cd /home/flightmare/flightrl/examples"
echo "  python3 generate_synthetic_flights.py --csv-out saved/Prueba.csv --steps=5000"
