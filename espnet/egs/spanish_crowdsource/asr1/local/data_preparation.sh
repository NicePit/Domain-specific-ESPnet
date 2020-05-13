#!/bin/bash

cd "$(dirname "$0")"
pip install -r requirements.txt

python3 make_data.py || exit 1

chmod -R 777 ../data
chmod -R 777 ../downloads


