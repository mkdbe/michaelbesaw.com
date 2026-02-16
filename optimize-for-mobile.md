# Quick Photo Optimization - New Photos

Simple instructions for optimizing photos when you add new images to the portfolio.

---

## Method 1: Optimize New Photos Only (Recommended)

### Step 1: Upload New Photos
```bash
# Upload via scp from your local machine
scp *.jpg user@server:/var/www/html/michaelbesaw.com/photos/
```

### Step 2: SSH into Server
```bash
ssh user@server
```

### Step 3: Optimize the New Photos
```bash
# Navigate to photos directory
cd /var/www/html/michaelbesaw.com/photos

# Optimize just the new photos (replace 'newphoto.jpg' with actual filename)
mogrify -resize '1200x1200>' -quality 70 -strip newphoto1.jpg
mogrify -resize '1200x1200>' -quality 70 -strip newphoto2.jpg
mogrify -resize '1200x1200>' -quality 70 -strip newphoto3.jpg
```

### Step 4: Fix Permissions
```bash
chmod 644 *.jpg
```

### Done!
Refresh your website - new photos will appear automatically.

---

## Method 2: Re-run Full Optimization Script

### Step 1: Upload New Photos
```bash
scp *.jpg user@server:/var/www/html/michaelbesaw.com/photos/
```

### Step 2: Run the Script
```bash
ssh user@server
cd /var/www/html/michaelbesaw.com
./optimize-for-mobile.sh
```

### Done!
Script will process all photos (including new ones).

---

## Method 3: One-Line Command for All New Photos

If you uploaded multiple new photos and want to optimize them all at once:

```bash
# SSH into server
ssh user@server

# Navigate to photos directory
cd /var/www/html/michaelbesaw.com/photos

# Optimize ALL jpg files in the directory
for img in *.jpg *.JPG *.jpeg *.JPEG; do
    [ -f "$img" ] && mogrify -resize '1200x1200>' -quality 70 -strip "$img"
done

# Fix permissions
chmod 644 *
```

---

## Quick Quality Check

After optimization, check file sizes:
```bash
ls -lh /var/www/html/michaelbesaw.com/photos/
```

**Good file sizes:**
- 200-500 KB per photo ✓
- 1-2 MB per photo (may be too large for mobile)

---

## If Something Goes Wrong

### Photos look too blurry?
Use higher quality:
```bash
mogrify -resize '1200x1200>' -quality 80 -strip yourphoto.jpg
```

### Need to restore original?
If you backed up originals:
```bash
cp /var/www/html/michaelbesaw.com/photos-backup/photo.jpg \
   /var/www/html/michaelbesaw.com/photos/
```

---

## That's It!

Just remember:
1. Upload photos
2. Run optimization command
3. Refresh website

**Tip:** Save this command in your notes for quick access:
```bash
cd /var/www/html/michaelbesaw.com/photos && for img in *.jpg; do mogrify -resize '1200x1200>' -quality 70 -strip "$img"; done
```
