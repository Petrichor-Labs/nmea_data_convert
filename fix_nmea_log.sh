#!/bin/bash

usage() {
    echo "Usage: $0 <input_file> [output_file]"
}

CYCLE_END="GAGSA"

# check if args are given
[[ $# > 0 ]] && file="$1" || { usage; exit 0; }
# check args
[[ "${file}" == "-h" || "${file}" == "--help" ]] && { usage; exit 0; }
# check if first arg is a readable file
[[ ! -r "${file}" ]] && { echo "Error: File ${file} not found!" 2>&1; usage; exit 1; }
# check if second arg exists, else construct output filename based on input filename
[[ -n "$2" ]] && output="$2" || output="${file%.*}_fixed.${file##*.}"

# list of sentences in the cycle
declare -a cycle
RMC=""

while read line; do
    # skip empty lines
    [[ ! -n "${line}" ]] && continue

    # get sentence type
    cs="${line%%,*}"
    cs="${cs#*$}"

    if [[ "${cs}" == "GPRMC" ]]; then
        # this sentence type should be placed at the start of the cycle
        RMC="${line}"
    elif [[ "${cs}" == "${CYCLE_END}" ]]; then
        # write sentences to output file in corrected order
        echo "${RMC}" >> "${output}"
        for item in "${cycle[@]}"; do
            echo "${item}" >> "${output}"
        done
        echo "${line}" >> "${output}"

        # clear list
        cycle=()
    else
        # add sentence to list
        cycle=( "${cycle[@]}" "${line}")
    fi
done < "${file}"

echo "Output writen to ${output}"
