#!/usr/bin/env bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="*"
export no_proxy="*"
exec "$@"
