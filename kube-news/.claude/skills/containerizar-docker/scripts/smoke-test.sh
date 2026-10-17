#!/usr/bin/env bash
# Smoke test HTTP: imprime "<código> <path>" para cada caminho.
# Uso: smoke-test.sh <base_url> [path...]
#   default de paths: /health /ready /metrics /
#   REPEAT=N  -> chama <HEALTH_PATH> N vezes e conta respostas distintas (balanceamento entre réplicas)
#   HEALTH_PATH (default /health)
# Sai com código 1 se algum path retornar >= 400 (exceto 302/3xx, considerados ok).
set -u

base="${1:?uso: smoke-test.sh <base_url> [path...]}"
shift
base="${base%/}"
case "$base" in http*) ;; *) base="http://$base" ;; esac

paths=("$@")
[ ${#paths[@]} -eq 0 ] && paths=(/health /ready /metrics /)

fail=0
for p in "${paths[@]}"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$base$p")
  echo "$code $p"
  if [ "$code" = "000" ] || [ "$code" -ge 400 ]; then fail=1; fi
done

if [ "${REPEAT:-0}" -gt 0 ]; then
  hp="${HEALTH_PATH:-/health}"
  echo "--- $REPEAT chamadas em $hp (respostas distintas):"
  for _ in $(seq 1 "$REPEAT"); do
    curl -s --max-time 5 "$base$hp"; echo
  done | sort | uniq -c
fi

exit $fail
