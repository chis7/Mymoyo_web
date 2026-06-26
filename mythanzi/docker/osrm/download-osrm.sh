#!/bin/sh
set -eu

DATA_DIR="${OSRM_DATA_DIR:-/data}"
BASE_NAME="${OSRM_BASE_NAME:-zambia-latest}"
PBF_URL="${OSRM_PBF_URL:-https://download.geofabrik.de/africa/zambia-latest.osm.pbf}"
MIN_PBF_BYTES="${OSRM_MIN_PBF_BYTES:-200000000}"

PBF_PATH="${DATA_DIR}/${BASE_NAME}.osm.pbf"
OSRM_PATH="${DATA_DIR}/${BASE_NAME}.osrm"

has_prepared_data() {
    for suffix in \
        "" \
        ".cell_metrics" \
        ".cells" \
        ".datasource_names" \
        ".edges" \
        ".fileIndex" \
        ".geometry" \
        ".icd" \
        ".mldgr" \
        ".names" \
        ".partition" \
        ".properties" \
        ".ramIndex" \
        ".timestamp" \
        ".turn_duration_penalties" \
        ".turn_weight_penalties"
    do
        if [ ! -s "${OSRM_PATH}${suffix}" ]; then
            return 1
        fi
    done

    return 0
}

if has_prepared_data; then
    echo "OSRM data already exists for ${BASE_NAME}; skipping download."
    exit 0
fi

mkdir -p "$DATA_DIR"

if [ -s "$PBF_PATH" ]; then
    pbf_size="$(wc -c < "$PBF_PATH" | tr -d ' ')"
    if [ "$pbf_size" -ge "$MIN_PBF_BYTES" ]; then
        echo "Using existing PBF at ${PBF_PATH} (${pbf_size} bytes)."
        exit 0
    fi

    echo "Existing PBF is too small (${pbf_size} bytes); replacing it."
fi

tmp_path="${PBF_PATH}.download"
rm -f "$tmp_path"

echo "Downloading ${PBF_URL} to ${PBF_PATH}"
curl \
    --location \
    --fail \
    --retry 5 \
    --retry-delay 10 \
    --connect-timeout 60 \
    --output "$tmp_path" \
    "$PBF_URL"

mv "$tmp_path" "$PBF_PATH"
echo "Downloaded ${PBF_PATH}."
