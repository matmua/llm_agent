#!/usr/bin/env bash
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY FTP_PROXY SOCKS_PROXY
unset http_proxy https_proxy all_proxy ftp_proxy socks_proxy
unset GIT_PROXY_COMMAND git_proxy_command
unset CURL_PROXY curl_proxy
unset PIP_PROXY pip_proxy
unset npm_config_proxy npm_config_https_proxy npm_config_http_proxy
export NO_PROXY="*"
export no_proxy="*"
exec "$@"
