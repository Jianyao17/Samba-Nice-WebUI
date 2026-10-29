#!/bin/sh
# Collect the Samba binaries and shared libraries used by the runtime image.
# Run in a builder stage where the samba package is already installed.
set -eu
OUT="${OUT:-/out}"
mkdir -p "$OUT/usr/bin" "$OUT/usr/lib/x86_64-linux-gnu/samba"

for binary in testparm pdbedit; do
  cp "/usr/bin/$binary" "$OUT/usr/bin/$binary"

  ldd "/usr/bin/$binary" | awk '/=>/ {print $3} /^\t\// {print $1}' | sort -u | while read -r lib; do
    case "$lib" in
      /lib64/ld-linux*) continue ;;   # interpreter already exists in base image
    esac
    case "$lib" in
      /usr/lib/x86_64-linux-gnu/samba/*) dest="$OUT/usr/lib/x86_64-linux-gnu/samba/$(basename "$lib")" ;;
      *)                                 dest="$OUT/usr/lib/x86_64-linux-gnu/$(basename "$lib")" ;;
    esac
    cp -L "$lib" "$dest"
  done
done
