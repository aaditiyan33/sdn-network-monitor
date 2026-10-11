#!/bin/bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf iperf3 tcpdump git python3-pip software-properties-common
if ! command -v python3.9 >/dev/null 2>&1; then
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt update
  sudo apt install -y python3.9 python3.9-venv python3.9-distutils
fi
[ -d ~/ryu-env ] || python3.9 -m venv ~/ryu-env
source ~/ryu-env/bin/activate
pip install --upgrade pip wheel
pip install "setuptools==57.5.0" wheel pbr
pip install eventlet==0.30.2 dnspython==1.16.0
PBR_VERSION=4.34 pip install ryu==4.34 --no-build-isolation
pip install eventlet==0.30.2
pip install matplotlib pandas
