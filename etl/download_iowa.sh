#!/bin/bash

# This script downloads all the necessary 2024 TIGER files for the state of Iowa.
# It fetches ADDRFEAT, EDGES, and FACES for each of Iowa's 99 counties,
# plus the statewide PLACE file and the national FEATNAMES and STATE files.

YEAR="2024"
STATE_FIPS="19"
DIR_NAME="iowa_tiger_${YEAR}_complete"

# An array of all 99 county FIPS codes for Iowa (State FIPS 19)
IOWA_COUNTIES=(
  "19001" "19003" "19005" "19007" "19009" "19011" "19013" "19015" "19017" "19019" "19021" "19023" "19025" "19027" "19029" "19031" "19033" "19035" "19037" "19039" "19041" "19043" "19045" "19047" "19049" "19051" "19053" "19055" "19057" "19059" "19061" "19063" "19065" "19067" "19069" "19071" "19073" "19075" "19077" "19079" "19081" "19083" "19085" "19087" "19089" "19091" "19093" "19095" "19097" "19099" "19101" "19103" "19105" "19107" "19109" "19111" "19113" "19115" "19117" "19119" "19121" "19123" "19125" "19127" "19129" "19131" "19133" "19135" "19137" "19139" "19141" "19143" "19145" "19147" "19149" "19151" "19153" "19155" "19157" "19159" "19161" "19163" "19165" "19167" "19169" "19171" "19173" "19175" "19177" "19179" "19181" "19183" "19185" "19187" "19189" "19191" "19193" "19195" "19197"
)

# Base URL for the TIGER/Line shapefiles
BASE_URL="https://www2.census.gov/geo/tiger/TIGER${YEAR}"

# Create a directory for the files and navigate into it
mkdir -p "$DIR_NAME"
cd "$DIR_NAME" || exit

# --- Download County-Level Files ---
echo "🚚 Downloading files for all 99 Iowa counties..."
for COUNTY_FIPS in "${IOWA_COUNTIES[@]}"; do
  echo "Fetching data for county ${COUNTY_FIPS}..."
  wget --no-check-certificate -q "${BASE_URL}/ADDRFEAT/tl_${YEAR}_${COUNTY_FIPS}_addrfeat.zip"
  wget --no-check-certificate -q "${BASE_URL}/EDGES/tl_${YEAR}_${COUNTY_FIPS}_edges.zip"
  wget --no-check-certificate -q "${BASE_URL}/FACES/tl_${YEAR}_${COUNTY_FIPS}_faces.zip"
done

# --- Download State and National Files ---
echo "🚚 Downloading state and national files..."
# State-level Place file
wget --no-check-certificate -q "${BASE_URL}/PLACE/tl_${YEAR}_${STATE_FIPS}_place.zip"
# National-level Feature Names file
wget --no-check-certificate -q "${BASE_URL}/FEATNAMES/tl_${YEAR}_us_featnames.zip"
# National-level State file
wget --no-check-certificate -q "${BASE_URL}/STATE/tl_${YEAR}_us_state.zip"

# --- Unzip and Clean Up ---
echo "📦 Unzipping all downloaded files..."
unzip -q '*.zip'

echo "🧹 Cleaning up zip archives..."
rm *.zip

echo "✅ Download and extraction complete. All files are in the '${DIR_NAME}' directory."