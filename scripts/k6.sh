#!/usr/bin/env bash
# Sourced by setup.sh and ensure.sh. k6 is a host binary (not pip, not Compose, not CI).

install_k6_if_needed() {
	if command -v k6 >/dev/null 2>&1; then
		echo "==> k6 ok"
		return 0
	fi
	echo "==> instalando k6"
	if command -v brew >/dev/null 2>&1; then
		brew install k6
		return 0
	fi
	echo "k6 ausente e sem Homebrew. Instale: https://grafana.com/docs/k6/latest/set-up/install-k6/" >&2
}
