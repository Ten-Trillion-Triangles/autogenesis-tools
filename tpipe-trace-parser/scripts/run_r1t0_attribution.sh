#!/bin/bash
set -e
[ -d /tmp/venv ] || python3 -m venv /tmp/venv
/tmp/venv/bin/pip install --quiet tiktoken
SKILL=/home/cage/.hermes/skills/software-development/tpipe-trace-parser
/tmp/venv/bin/python $SKILL/scripts/autogenesis_attribution.py \
    --dir /home/cage/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/ \
    --json /tmp/r1t0-attribution.json