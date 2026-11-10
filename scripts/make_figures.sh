#!/usr/bin/env bash
# Regenerate the artifact crops and annotated overview images from the
# originals. Requires ImageMagick 7 (`magick`).
#
# Crops are square regions upscaled to 600x600 with nearest-neighbour
# sampling (-filter point) so individual detector pixels stay visible.
set -euo pipefail

cd "$(dirname "$0")/.."
orig=images/originals
crops=images/crops
annot=images/annotated
mkdir -p "$crops" "$annot"

# name | source file | crop size | x offset | y offset
artifacts=(
  "A1_euvi195_2010-04-25|20100425_111030_n4euA_195.jpg|75|1972|1032"
  "A2_aia335_2013-02-24|20130224_230140_4096_0335.jpg|600|3496|860"
  "A3_aia193_2017-06-20|20170620_125617_4096_0193.jpg|100|0|1225"
  "A4a_aia304_2019-06-28_upper|20190628_140035_4096_304211171.jpg|150|73|755"
  "A4b_aia304_2019-06-28_lower|20190628_140035_4096_304211171.jpg|100|8|3600"
)

for a in "${artifacts[@]}"; do
  IFS='|' read -r name src size x y <<<"$a"
  magick "$orig/$src" -crop "${size}x${size}+${x}+${y}" +repage \
    -filter point -resize 600x600 "$crops/$name.png"
done

# Annotated overviews: 1024px wide, yellow box around each crop region.
annotate() {
  local src=$1; shift
  local w scale draw=()
  w=$(magick identify -format '%w' "$orig/$src")
  scale=$(( w / 1024 ))
  for box in "$@"; do
    IFS='|' read -r label size x y <<<"$box"
    local x0=$(( x / scale - 4 )) y0=$(( y / scale - 4 ))
    local x1=$(( (x + size) / scale + 4 )) y1=$(( (y + size) / scale + 4 ))
    (( x0 < 1 )) && x0=1
    (( x1 > 1022 )) && x1=1022
    local tx=$(( x0 < 980 ? x0 : 980 ))
    local ty=$(( y0 > 20 ? y0 - 6 : y1 + 18 ))
    draw+=(-stroke yellow -strokewidth 2 -fill none
           -draw "rectangle $x0,$y0 $x1,$y1"
           -stroke none -fill yellow -pointsize 18
           -draw "text $tx,$ty '$label'")
  done
  magick "$orig/$src" -resize 1024x1024 "${draw[@]}" \
    "$annot/${src%.jpg}_annotated.jpg"
}

annotate 20100425_111030_n4euA_195.jpg      "A1|75|1972|1032"
annotate 20130224_230140_4096_0335.jpg      "A2|600|3496|860"
annotate 20170620_125617_4096_0193.jpg      "A3|100|0|1225"
annotate 20190628_140035_4096_304211171.jpg "A4a|150|73|755" "A4b|100|8|3600"
