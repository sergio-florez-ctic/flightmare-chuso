#!/usr/bin/env python3
import argparse
import os
from scipy.spatial.transform import Rotation as Rot
from scipy.ndimage import gaussian_filter1d
import numpy as np
import pandas as pd
from ruamel.yaml import YAML, dump, RoundTripDumper

from flightgym import QuadrotorEnv_v1
from rpg_baselines.envs import vec_env_wrapper as wrapper

def smoothstep(edge0, edge1, x):
    """Interpolacion suave para evitar tirones de aceleracion."""
    x = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return x * x * (3 - 2 * x)

def parser():
    parser = argparse.ArgumentParser(description="Generador de vuelos sinteticos (Z=100 constante).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--csv-out", type=str,
                        default=os.path.join(os.path.dirname(__file__), "saved", "vuelo_z100_estable.csv"))
    parser.add_argument("--dt", type=float, default=0.01)
    parser.add_argument("--noise-accel", type=float, default=0.02)
    parser.add_argument("--rw-accel", type=float, default=0.001)
    parser.add_argument("--noise-gyro", type=float, default=0.005)
    parser.add_argument("--rw-gyro", type=float, default=0.0001)
    parser.add_argument('--steps', type=int, default=8000, help='Number of steps')
    return parser

def make_env(args):
    cfg_path = os.path.join(os.environ["FLIGHTMARE_PATH"],
                            "flightlib", "configs", "vec_env.yaml")
    cfg = YAML().load(open(cfg_path, "r"))
    
    cfg["env"]["seed"] = args.seed
    cfg["env"]["scene_id"] = 0
    cfg["env"]["num_envs"] = 1  
    cfg["env"]["num_threads"] = 1
    cfg["env"]["render"] = "no" 

    env = wrapper.FlightEnvVec(
        QuadrotorEnv_v1(dump(cfg, Dumper=RoundTripDumper), False))
    env.seed(args.seed)
    return env, cfg

def main():
    args = parser().parse_args()
    np.random.seed(args.seed)

    env, cfg = make_env(args)
    obs = env.reset()

    # --- DISEÑO FÍSICO DE LA TRAYECTORIA ---
    # En NED, Z negativa es hacia arriba.
    # El dron empieza en (0, 0, -10) tras reset (10m de altura, orientado al norte).
    # Queremos subir a ~150m (z=-150) y luego serpentear.
    
    H_START = 10.0      # Donde empieza el dron (z=10 tras reset = 10m altura)
    H_CRUISE = 100.0    # Altura de crucero (100m, pedido por el usuario)
    total_steps = max(args.steps, 8000) # Forzar mínimo para que dé tiempo a todas las fases
    
    # Fases: hover inicial -> ascenso -> hover -> crucero -> hover -> descenso -> hover
    steps_hover_init = 100   # 1s estabilización inicial
    steps_ascent = 2500      # 25s para subir 90m
    steps_hover_top = 200    # 2s estabilización arriba
    steps_hover_end = 200    # 2s estabilización antes de bajar
    steps_descent = 2500     # 25s para bajar 90m
    steps_hover_bottom = 100 # 1s en el suelo
    
    steps_cruise = total_steps - steps_hover_init - steps_ascent - steps_hover_top - steps_hover_end - steps_descent - steps_hover_bottom
    
    target_x = np.zeros(total_steps)
    target_y = np.zeros(total_steps)
    target_z = np.zeros(total_steps)
    
    curr_step = 0
    
    # Fase 0: Hover inicial
    for i in range(steps_hover_init):
        target_z[curr_step] = H_START
        target_x[curr_step] = 0.0
        target_y[curr_step] = 0.0
        curr_step += 1

    # Fase 1: Subida VERTICAL suave
    for i in range(steps_ascent):
        prog = i / steps_ascent
        target_z[curr_step] = H_START + (H_CRUISE - H_START) * smoothstep(0, 1, prog)
        target_x[curr_step] = 0.0
        target_y[curr_step] = 0.0
        curr_step += 1
    
    # Fase 1.5: Hover arriba
    for i in range(steps_hover_top):
        target_z[curr_step] = H_CRUISE
        target_x[curr_step] = 0.0
        target_y[curr_step] = 0.0
        curr_step += 1

    # Fase 2: Misión estructurada (tramos rectos y curvas)
    # Generamos un perfil de "velocidad de giro" (yaw rate) y lo integramos.
    
    # Semilla determinista (puedes cambiar este número para generar otra misión distinta pero reproducible)
    np.random.seed(args.seed)
    
    turn_rates = np.zeros(steps_cruise)
    idx = 0
    
    while idx < steps_cruise:
        # 1. Tramo recto (sin giro)
        straight_duration = np.random.uniform(3.0, 8.0) # Entre 3 y 8 segundos recto
        straight_steps = int(straight_duration / args.dt)
        # turn_rates ya es 0, así que solo avanzamos el índice
        idx += straight_steps
        
        if idx >= steps_cruise:
            break
            
        # 2. Curva (giro constante)
        turn_duration = np.random.uniform(3.0, 7.0) # Entre 3 y 7 segundos de curva
        turn_steps = int(turn_duration / args.dt)
        
        # Elegir un giro entre 15 y 35 grados por segundo
        turn_rate = np.random.uniform(np.radians(15), np.radians(35))
        turn_rate *= np.random.choice([-1, 1]) # Izquierda o derecha aleatoriamente
        
        end_idx = min(idx + turn_steps, steps_cruise)
        turn_rates[idx:end_idx] = turn_rate
        idx = end_idx

    # Suavizar las transiciones entre rectas y curvas para que los cambios de dirección no sean instantáneos
    smooth_turn_rates = gaussian_filter1d(turn_rates, sigma=50) # 0.5s de transición (fuerza G manejable)

    # Integrar la velocidad de giro para obtener el rumbo (heading) a lo largo del tiempo
    headings = np.cumsum(smooth_turn_rates) * args.dt
    
    # Velocidad de avance constante (ej. 5 m/s)
    speed = 5.0
    
    # Descomponer en X e Y
    vx_cruise = speed * np.sin(headings) # X es el eje transversal
    vy_cruise = speed * np.cos(headings) # Y es el eje frontal
        
    # Fade in y Fade out para empezar y terminar sin tirones bruscos
    fade_len = min(200, steps_cruise // 4)
    fade_in = np.linspace(0, 1, fade_len)
    fade_out = np.linspace(1, 0, fade_len)
    
    vx_cruise[:fade_len] *= fade_in
    vy_cruise[:fade_len] *= fade_in
    vx_cruise[-fade_len:] *= fade_out
    vy_cruise[-fade_len:] *= fade_out
    
    for i in range(steps_cruise):
        target_z[curr_step] = H_CRUISE
        
        # Integrar las velocidades para obtener la posición objetivo
        target_x[curr_step] = target_x[curr_step - 1] + vx_cruise[i] * args.dt
        target_y[curr_step] = target_y[curr_step - 1] + vy_cruise[i] * args.dt
        
        curr_step += 1

    # Guardamos donde termina el serpenteo para bajar en esa misma posición XY
    last_x = target_x[curr_step - 1]
    last_y = target_y[curr_step - 1]

    # Fase 3: Hover antes de descender
    for i in range(steps_hover_end):
        target_z[curr_step] = H_CRUISE
        target_x[curr_step] = last_x
        target_y[curr_step] = last_y
        curr_step += 1

    # Fase 4: Descenso VERTICAL
    for i in range(steps_descent):
        prog = i / steps_descent
        target_z[curr_step] = H_CRUISE - (H_CRUISE - H_START) * smoothstep(0, 1, prog)
        target_x[curr_step] = last_x
        target_y[curr_step] = last_y
        curr_step += 1

    # Fase 5: Hover en el fondo
    for i in range(steps_hover_bottom):
        target_z[curr_step] = H_START
        target_x[curr_step] = last_x
        target_y[curr_step] = last_y
        curr_step += 1

    # Recortar arrays al tamaño real
    target_x = target_x[:curr_step]
    target_y = target_y[:curr_step]
    target_z = target_z[:curr_step]
    total_steps = curr_step
    
    # Arrays de grabación
    observations = np.zeros((total_steps, env.num_obs), dtype=np.float32)
    imu_accel_noisy = np.zeros((total_steps, 3), dtype=np.float32)
    imu_gyro_noisy = np.zeros((total_steps, 3), dtype=np.float32)

    bias_accel = np.zeros(3, dtype=np.float32)
    bias_gyro = np.zeros(3, dtype=np.float32)
    prev_vel = np.zeros(3, dtype=np.float32)

    # Velocidades feedforward (derivada de la trayectoria)
    target_vx = np.gradient(target_x, args.dt)
    target_vy = np.gradient(target_y, args.dt)
    target_vz = np.gradient(target_z, args.dt)
    
    # CLAMP las velocidades feedforward para que no sean absurdas
    max_ff_xy = 5.0
    max_ff_z = 8.0
    target_vx = np.clip(target_vx, -max_ff_xy, max_ff_xy)
    target_vy = np.clip(target_vy, -max_ff_xy, max_ff_xy)
    target_vz = np.clip(target_vz, -max_ff_z, max_ff_z)

    print(f"Simulando {total_steps} pasos ({total_steps * args.dt:.1f}s)")
    print(f"  Hover init: {steps_hover_init} pasos")
    print(f"  Ascenso: {steps_ascent} pasos (H_START={H_START} -> H_CRUISE={H_CRUISE})")
    print(f"  Hover top: {steps_hover_top} pasos")
    print(f"  Crucero: {steps_cruise} pasos")
    print(f"  Descenso: {steps_descent} pasos (H_CRUISE={H_CRUISE} -> H_START={H_START})")

    ORIGIN_LAT, ORIGIN_LON = 43.5322, -5.6611
    METERS_PER_DEG_LAT = 111320.0
    METERS_PER_DEG_LON = 111320.0 * np.cos(np.radians(ORIGIN_LAT))

    n_resets = 0
    
    for step in range(total_steps):
        state = obs[0]
        # En C++, getObs hace: euler_zyx = eulerAngles(2, 1, 0)
        # Esto significa que obs[3] = Yaw, obs[4] = Pitch, obs[5] = Roll
        x, y, z = state[0], state[1], state[2]
        yaw_raw, pitch_raw, roll_raw = state[3], state[4], state[5]
        
        # Corregir la discontinuidad de Eigen (Euler angles [pi, pi, pi] == [0, 0, 0])
        rot = Rot.from_euler('zyx', [yaw_raw, pitch_raw, roll_raw])
        yaw, pitch, roll = rot.as_euler('zyx')
        vx, vy, vz = state[6], state[7], state[8]
        p, q, r = state[9], state[10], state[11]

        # --- DEBUG cada 200 pasos ---
        if step % 200 == 0:
            err_pos = np.sqrt((target_x[step]-x)**2 + (target_y[step]-y)**2 + (target_z[step]-z)**2)
            print(f"  [{step:5d}] pos=({x:.1f},{y:.1f},{z:.1f}) target=({target_x[step]:.1f},{target_y[step]:.1f},{target_z[step]:.1f}) "
                  f"err={err_pos:.1f}m vel=({vx:.1f},{vy:.1f},{vz:.1f}) att=({np.degrees(roll):.1f},{np.degrees(pitch):.1f},{np.degrees(yaw):.1f})deg resets={n_resets}")

        # =============================================
        # CONTROLADOR PID EN CASCADA
        # =============================================
        
        # --- Z (Altura) ---
        err_z = target_z[step] - z
        target_vz_cmd = np.clip(0.8 * err_z + target_vz[step], -4.0, 4.0)
        err_vz = target_vz_cmd - vz
        # hover_thrust = mass * g = 0.73 * 9.81 ≈ 7.16 N
        cmd_thrust = np.clip(7.16 + 1.0 * err_vz, 2.0, 15.0)

        # --- XY (Posición lateral) ---
        err_x = target_x[step] - x
        err_y = target_y[step] - y
        
        # Pos -> Vel deseada (ganancia más baja para evitar sobrecorrección)
        target_vx_cmd = np.clip(0.5 * err_x + target_vx[step], -4.0, 4.0)
        target_vy_cmd = np.clip(0.5 * err_y + target_vy[step], -4.0, 4.0)
        
        # Vel -> Ángulo deseado (MUCHO MÁS CONSERVADOR: max ~8 grados)
        max_angle = 0.15
        target_pitch = np.clip( 0.04 * (target_vx_cmd - vx), -max_angle, max_angle)
        target_roll  = np.clip(-0.04 * (target_vy_cmd - vy), -max_angle, max_angle)
        
        # Ángulo -> Rate deseado
        target_p = np.clip(3.0 * (target_roll - roll), -2.0, 2.0)
        target_q = np.clip(3.0 * (target_pitch - pitch), -2.0, 2.0)
        
        # Rate -> Momentos
        # --- Yaw (siempre apuntando al norte) ---
        target_yaw = 0.0
        diff_yaw = (target_yaw - yaw + np.pi) % (2 * np.pi) - np.pi
        cmd_yaw = np.clip(0.05 * diff_yaw - 0.05 * r, -0.05, 0.05)
        
        cmd_roll  = np.clip(0.05 * (target_p - p), -0.05, 0.05)
        cmd_pitch = np.clip(0.05 * (target_q - q), -0.05, 0.05)

        # --- Mezclador de motores ---
        T = cmd_thrust / 4.0
        R = cmd_roll
        P = cmd_pitch
        Y = cmd_yaw
        
        m1_cmd = T + R - P + Y
        m2_cmd = T - R - P - Y
        m3_cmd = T - R + P + Y
        m4_cmd = T + R + P - Y
        
        # Prevención de saturación (El límite real del simulador es act=1.0 -> 5.37 N)
        max_limit = 5.37
        max_cmd = max(m1_cmd, m2_cmd, m3_cmd, m4_cmd)
        min_cmd = min(m1_cmd, m2_cmd, m3_cmd, m4_cmd)
        if max_cmd > max_limit:
            offset = max_cmd - max_limit
            m1_cmd -= offset
            m2_cmd -= offset
            m3_cmd -= offset
            m4_cmd -= offset
        if min_cmd < 0.0:
            offset = -min_cmd
            m1_cmd += offset
            m2_cmd += offset
            m3_cmd += offset
            m4_cmd += offset
            
        m1 = np.clip(m1_cmd, 0.0, max_limit)
        m2 = np.clip(m2_cmd, 0.0, max_limit)
        m3 = np.clip(m3_cmd, 0.0, max_limit)
        m4 = np.clip(m4_cmd, 0.0, max_limit)

        # Conversión a espacio de acciones del simulador
        act_m1 = (m1 - 1.790325) / 3.58065
        act_m2 = (m2 - 1.790325) / 3.58065
        act_m3 = (m3 - 1.790325) / 3.58065
        act_m4 = (m4 - 1.790325) / 3.58065

        action = np.array([[act_m1, act_m2, act_m3, act_m4]], dtype=np.float32)
        action = np.clip(action, -1.0, 1.0) # Asegurar que la red no sature el límite físico del simulador de C++
        next_obs, _, done, _ = env.step(action)

        # Generación de ruido IMU
        gt_vel = state[6:9]   
        gt_gyro = state[9:12] 
        gt_accel = (gt_vel - prev_vel) / args.dt
        prev_vel = np.copy(gt_vel)

        bias_accel += np.random.normal(0, args.rw_accel, 3) * args.dt
        bias_gyro += np.random.normal(0, args.rw_gyro, 3) * args.dt
        white_noise_accel = np.random.normal(0, args.noise_accel, 3)
        white_noise_gyro = np.random.normal(0, args.noise_gyro, 3)
        
        observations[step] = state
        imu_accel_noisy[step] = gt_accel + bias_accel + white_noise_accel
        imu_gyro_noisy[step] = gt_gyro + bias_gyro + white_noise_gyro

        if done[0]:
            n_resets += 1
            # NOTA: el C++ ya ha reseteado el dron y actualizado obs dentro de env.step()
            # NO llamamos a env.reset() de nuevo, solo usamos next_obs que ya contiene el estado post-reset
            print(f"  *** RESET #{n_resets} en step {step}! Pos era ({x:.1f},{y:.1f},{z:.1f}), "
                  f"target era ({target_x[step]:.1f},{target_y[step]:.1f},{target_z[step]:.1f})")
            bias_accel = np.zeros(3, dtype=np.float32)
            bias_gyro  = np.zeros(3, dtype=np.float32)
            prev_vel   = np.zeros(3, dtype=np.float32)

        obs = next_obs

    print(f"\nSimulacion completada. Total resets: {n_resets}")

    # --- EXPORTACION AL CSV ---
    os.makedirs(os.path.dirname(os.path.abspath(args.csv_out)), exist_ok=True)
    # Convertir a float64 ANTES de sumar para evitar pérdida de precisión (cuadraditos/escaleras)
    lat_array = ORIGIN_LAT + (observations[:, 1].astype(np.float64) / METERS_PER_DEG_LAT)
    lon_array = ORIGIN_LON + (observations[:, 0].astype(np.float64) / METERS_PER_DEG_LON)
    
    df = pd.DataFrame({
        'Lat': lat_array, 'Lon': lon_array, 'Alt': observations[:, 2],
        'PosX': observations[:, 0], 'PosY': observations[:, 1],
        'Heading': observations[:, 5], 
        'VEast': observations[:, 6], 'VNorth': observations[:, 7], 'VUp': observations[:, 8],
        'Target_PosX': target_x, 'Target_PosY': target_y, 'Target_VZ': target_z,
        'Target_VX': target_vx, 'Target_VY': target_vy, 'Target_VZ_vel': target_vz,
        'imu_accel_x': imu_accel_noisy[:, 0], 'imu_accel_y': imu_accel_noisy[:, 1], 'imu_accel_z': imu_accel_noisy[:, 2],
        'RollRate': imu_gyro_noisy[:, 0], 'PitchRate': imu_gyro_noisy[:, 1], 'imu_gyro_z': imu_gyro_noisy[:, 2] 
    })
    
    df.to_csv(args.csv_out, index=False)
    print(f"Dataset guardado en: {args.csv_out}")

if __name__ == "__main__":
    main()