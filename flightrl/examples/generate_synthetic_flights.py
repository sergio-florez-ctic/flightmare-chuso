#!/usr/bin/env python3
import argparse
import os

import numpy as np
from ruamel.yaml import YAML, dump, RoundTripDumper

from flightgym import QuadrotorEnv_v1
from rpg_baselines.envs import vec_env_wrapper as wrapper


def parser():
    parser = argparse.ArgumentParser(
        description="Generate synthetic quadrotor rollouts from Flightmare.")
    parser.add_argument("--steps", type=int, default=10000,
                        help="Number of simulation steps to record.")
    parser.add_argument("--num-envs", type=int, default=100,
                        help="Parallel simulated quadrotors.")
    parser.add_argument("--num-threads", type=int, default=10,
                        help="Flightmare worker threads.")
    parser.add_argument("--scene-id", type=int, default=0,
                        help="Unity scene id stored in the config.")
    parser.add_argument("--seed", type=int, default=1,
                        help="Random seed.")
    parser.add_argument("--out", type=str,
                        default=os.path.join(os.path.dirname(__file__),
                                             "saved",
                                             "synthetic_flights.npz"),
                        help="Output .npz path.")
    return parser


def make_env(args):
    cfg_path = os.path.join(os.environ["FLIGHTMARE_PATH"],
                            "flightlib",
                            "configs",
                            "vec_env.yaml")
    cfg = YAML().load(open(cfg_path, "r"))
    cfg["env"]["seed"] = args.seed
    cfg["env"]["scene_id"] = args.scene_id
    cfg["env"]["num_envs"] = args.num_envs
    cfg["env"]["num_threads"] = args.num_threads
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

    observations = np.zeros((args.steps, env.num_envs, env.num_obs),
                            dtype=np.float32)
    next_observations = np.zeros_like(observations)
    actions = np.zeros((args.steps, env.num_envs, env.num_acts),
                       dtype=np.float32)
    rewards = np.zeros((args.steps, env.num_envs), dtype=np.float32)
    dones = np.zeros((args.steps, env.num_envs), dtype=np.bool_)

    for step in range(args.steps):
        action = env.sample_actions()
        next_obs, reward, done, _ = env.step(action)

        observations[step] = obs
        actions[step] = action
        rewards[step] = reward
        dones[step] = done
        next_observations[step] = next_obs

        obs = env.reset() if np.any(done) else next_obs

        if (step + 1) % 1000 == 0:
            print("recorded {}/{} steps".format(step + 1, args.steps))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    np.savez_compressed(
        args.out,
        observations=observations,
        actions=actions,
        rewards=rewards,
        dones=dones,
        next_observations=next_observations,
        extra_info_names=np.asarray(env.extra_info_names),
        config=np.asarray([dump(cfg, Dumper=RoundTripDumper)]),
    )
    env.close()
    print("saved {}".format(args.out))


if __name__ == "__main__":
    main()
