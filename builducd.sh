#!/usr/bin/env bash

LATEST=$(python tools/pullucd.py --version)

python tools/pullucd.py "$@" --multiple -v "$LATEST" -d ucd

for dir in ucd/*/; do
	V=$(basename "$dir")
	if [ ! -f "ucd/full-$V.ucd" ]; then
		python tools/pypuaa.py compile -o "ucd/full-$V.ucd" -d "$dir"
	fi
	if [ ! -f "ucd/min-$V.ucd" ]; then
		python tools/pypuaa.py compile -o "ucd/min-$V.ucd" -d "$dir/Blocks.txt" -d "$dir/UnicodeData.txt"
	fi
	if [ ! -f "ucd/names-$V.ucd" ]; then
		python tools/pypuaa.py compile -o "ucd/names-$V.ucd" -d "$dir/Blocks.txt" -d "$dir/UnicodeData.txt" -d "$dir/NameAliases.txt"
	fi
done

cp "ucd/names-$LATEST.ucd" tools/unidata.ucd
