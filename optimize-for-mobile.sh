#!/bin/bash

# Mobile Image Optimization Script
# This script creates mobile-optimized versions of your photos

PHOTOS_DIR="/var/www/html/michaelbesaw.com/photos"
MOBILE_DIR="/var/www/html/michaelbesaw.com/photos-mobile"

echo "Creating mobile-optimized images..."

# Create mobile directory if it doesn't exist
mkdir -p "$MOBILE_DIR"

# Counter
count=0

# Process each image - handle different extensions separately
for ext in jpg JPG jpeg JPEG png PNG; do
    for img in "$PHOTOS_DIR"/*.$ext; do
        # Check if file exists (glob may not match)
        [ -f "$img" ] || continue
        
        filename=$(basename "$img")
        
        echo "Processing: $filename"
        
        # Create mobile version: max 1200px width, 75% quality, strip metadata
        convert "$img" \
            -resize '1200x1200>' \
            -quality 75 \
            -strip \
            "$MOBILE_DIR/$filename"
        
        count=$((count + 1))
    done
done

echo "Optimized $count images for mobile"
echo "Mobile images saved to: $MOBILE_DIR"
echo ""
echo "File sizes comparison:"
echo "Desktop images:"
du -sh "$PHOTOS_DIR"
echo "Mobile images:"
du -sh "$MOBILE_DIR"
