FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive 

# Installing some essential system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
   lsb-release \
   build-essential \
   python3 python3-dev python3-pip \
   cmake \
   git \
   vim \
   ca-certificates \
   libzmqpp-dev \
   libopencv-dev \
   gnupg2 \
   && rm -rf /var/lib/apt/lists/*

RUN /bin/bash -c 'echo "deb http://packages.ros.org/ros/ubuntu $(lsb_release -sc) main" > /etc/apt/sources.list.d/ros-latest.list' && \
    apt-key adv --keyserver 'hkp://keyserver.ubuntu.com:80' --recv-key C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654 

# Installing ROS  Melodic
RUN apt-get update && apt-get install -y --no-install-recommends \
   ros-melodic-desktop-full 

# Installing catkin tools
RUN apt-get update && apt-get install -y python3-setuptools && pip3 install catkin-tools 

WORKDIR /home
RUN git clone https://github.com/uzh-rpg/flightmare.git \
    && sed -i 's/GIT_TAG           master/GIT_TAG           v2.10.4/' \
        /home/flightmare/flightlib/cmake/pybind11_download.cmake \
    && sed -i 's/GIT_TAG           master/GIT_TAG           yaml-cpp-0.7.0/' \
        /home/flightmare/flightlib/cmake/yaml_download.cmake \
    && sed -i 's/option(BUILD_TESTS "Building the tests" ON)/option(BUILD_TESTS "Building the tests" OFF)/' \
        /home/flightmare/flightlib/CMakeLists.txt \
    && sed -i 's/option(BUILD_UNITY_BRIDGE_TESTS "Building the Unity Bridge tests" ON)/option(BUILD_UNITY_BRIDGE_TESTS "Building the Unity Bridge tests" OFF)/' \
        /home/flightmare/flightlib/CMakeLists.txt \
    && sed -i "s/packages=\['rpg_baselines'\]/packages=find_packages()/" \
        /home/flightmare/flightrl/setup.py \
    && touch /home/flightmare/flightrl/rpg_baselines/__init__.py \
        /home/flightmare/flightrl/rpg_baselines/common/__init__.py \
        /home/flightmare/flightrl/rpg_baselines/ppo/__init__.py \
        /home/flightmare/flightrl/rpg_baselines/envs/__init__.py

ENV FLIGHTMARE_PATH=/home/flightmare

# Python 3.6 (Ubuntu 18.04): pin deps incompatible with latest pip packages
RUN pip3 install --upgrade pip setuptools wheel \
    && pip3 install "opencv-python==4.2.0.32" "tensorflow==1.15.5" \
    && pip3 install /home/flightmare/flightlib \
    && pip3 install /home/flightmare/flightrl \
    && pip3 install "ruamel.yaml==0.17.32"