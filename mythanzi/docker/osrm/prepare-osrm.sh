#!/bin/sh
set -eu

DATA_DIR="${OSRM_DATA_DIR:-/data}"
BASE_NAME="${OSRM_BASE_NAME:-zambia-latest}"
PROFILE="${OSRM_PROFILE:-/opt/car.lua}"

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
    echo "OSRM data already exists for ${BASE_NAME}; skipping preparation."
    exit 0
fi

mkdir -p "$DATA_DIR"

if [ ! -s "$PBF_PATH" ]; then
    echo "Missing ${PBF_PATH}. Run the osrm-download service first." >&2
    exit 1
fi

pbf_size="$(wc -c < "$PBF_PATH" | tr -d ' ')"
echo "Using existing PBF at ${PBF_PATH} (${pbf_size} bytes)."

echo "Removing stale OSRM outputs for ${BASE_NAME}."
rm -f "${OSRM_PATH}" "${OSRM_PATH}".*

echo "Running osrm-extract."
osrm-extract -p "$PROFILE" "$PBF_PATH"

echo "Running osrm-partition."
osrm-partition "$OSRM_PATH"

echo "Running osrm-customize."
osrm-customize "$OSRM_PATH"

echo "OSRM data is ready at ${OSRM_PATH}."
