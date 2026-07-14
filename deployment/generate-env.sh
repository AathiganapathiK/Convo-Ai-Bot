#!/bin/bash

HOST_IP=$(ip route | awk '/default/ {print $3}')

cp .env.example .env.local

sed -i "s/^DB_HOST=.*/DB_HOST=${HOST_IP}/" .env.local

echo "Generated .env.local with DB_HOST=${HOST_IP}"