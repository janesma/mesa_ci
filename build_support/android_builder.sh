#!/bin/bash
# This is a helper script for building Android.

# The following (required) env variables should be set prior to running
# this script:
src=$ANDROID_SOURCE
target=$ANDROID_TARGET
module=$ANDROID_MODULE
num_cpus=${NUM_CPUS:-1}
# This seems to be required after updating to libc 2.27:
export LANG=C
set -e

function build(){
	lunch "$target"
	make -j "$num_cpus" "$module"
}


function clean(){
	make clean
}

cd "$src"
. "${src}/build/envsetup.sh"

if [[ $# -lt 1 ]]; then
		echo "Usage: ./android_builder.sh <clean, build>"
		exit 1
fi

case $1 in
	"clean")
			clean
			;;
	"build")
			build
			;;
	*)
			echo "Unknown command: $1"
			exit 1
			;;
esac
