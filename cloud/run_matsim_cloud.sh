#!/bin/bash
# MATSim large-scale simulation on cloud instance
#
# Target: AWS EC2 r6g.4xlarge (128GB RAM, 16 vCPU) — ~$1/hour
#         or r6g.8xlarge (256GB RAM) for 5M+ agents — ~$2/hour
#
# Usage:
#   1. Launch EC2 instance (Amazon Linux 2023 or Ubuntu 22.04)
#   2. scp this directory to the instance
#   3. ssh into instance and run: bash cloud/run_matsim_cloud.sh
#
# Estimated costs:
#   100K agents:  128GB, ~15 min  → ~$0.25
#   500K agents:  128GB, ~1 hour  → ~$1.00
#   1M agents:    256GB, ~3 hours → ~$6.00

set -euo pipefail

AGENTS=${AGENTS:-500000}
ITERATIONS=${ITERATIONS:-10}
JVM_MEMORY=${JVM_MEMORY:-96g}
SAMPLE_RATE=${SAMPLE_RATE:-0.01}

echo "================================================"
echo "MATSim Cloud Run"
echo "  Agents: $AGENTS"
echo "  Iterations: $ITERATIONS"
echo "  JVM Memory: $JVM_MEMORY"
echo "  Sample Rate: $SAMPLE_RATE"
echo "================================================"

# --- Install dependencies ---
echo "Installing dependencies..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3 python3-pip python3-venv openjdk-21-jdk unzip wget
elif command -v yum &>/dev/null; then
    sudo yum install -y python3 python3-pip java-21-amazon-corretto-devel unzip wget
fi

# --- Setup Python environment ---
echo "Setting up Python..."
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
pip install -q osmnx networkx geopandas shapely pyproj lxml requests tqdm

# --- Download MATSim if needed ---
MATSIM_DIR="data/matsim/matsim-2025.0"
if [ ! -f "$MATSIM_DIR/matsim-2025.0.jar" ]; then
    echo "Downloading MATSim 2025.0..."
    mkdir -p data/matsim
    cd data/matsim
    wget -q "https://github.com/matsim-org/matsim-libs/releases/download/2025.0/matsim-2025.0-release.zip"
    unzip -q matsim-2025.0-release.zip
    cd ../..
fi

# --- Run pipeline ---
echo "Running MATSim full-network pipeline..."
python scripts/run_matsim_fullnetwork.py \
    --agents "$AGENTS" \
    --iterations "$ITERATIONS" \
    --jvm-memory "$JVM_MEMORY" \
    --sample-rate "$SAMPLE_RATE" \
    --java-path "$(which java)" \
    --output-dir "data/output/matsim_cloud" \
    -v

echo "================================================"
echo "Done! Results in data/output/matsim_cloud/"
echo "Download viz data:"
echo "  scp -r instance:$(pwd)/data/output/matsim_cloud/viz/ ./web/data/"
echo "================================================"
