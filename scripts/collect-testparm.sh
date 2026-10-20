#!/bin/sh
# Collect the testparm binary and all shared libraries it requires.
# Run in a builder stage where samba-common-bin is already installed.
set -eu
OUT="${OUT:-/out}"
mkdir -p "$OUT/usr/bin" "$OUT/usr/lib/x86_64-linux-gnu/samba"
cp /usr/bin/testparm "$OUT/usr/bin/testparm"

ldd /usr/bin/testparm | awk '/=>/ {print $3} /^\t\// {print $1}' | sort -u | while read -r lib; do
  case "$lib" in
    /lib64/ld-linux*) continue ;;   # interpreter already exists in base image
  esac
  case "$lib" in
    /usr/lib/x86_64-linux-gnu/samba/*) dest="$OUT/usr/lib/x86_64-linux-gnu/samba/$(basename "$lib")" ;;
    *)                                 dest="$OUT/usr/lib/x86_64-linux-gnu/$(basename "$lib")" ;;
  esac
  cp -L "$lib" "$dest"
done
