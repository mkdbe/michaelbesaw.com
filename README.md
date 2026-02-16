# Michael Besaw Photography Portfolio

A beautiful full-screen photography portfolio that automatically displays images from a directory in random order with minimal, elegant navigation.

## Features

- 🖼️ **Automatic Image Loading** - Just drop photos in the `photos` folder
- 🔀 **Random Order** - Images shuffle on every page load
- 👻 **Minimal UI** - Title and navigation only appear when needed
- 📱 **Touch/Swipe Support** - Swipe left/right on touchscreens and touchpads
- 🖱️ **Mouse Drag** - Click and drag to navigate
- ⌨️ **Keyboard Navigation** - Arrow keys to browse
- ℹ️ **About Page** - Customizable overlay with portfolio information
- 🎨 **Zone-based Navigation** - Arrows appear only in their respective screen zones

## Setup

1. **Install Node.js** (if you haven't already)
   - Download from https://nodejs.org/

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Add your photos:**
   - A `photos` folder will be created automatically when you start the server
   - Add your image files (.jpg, .jpeg, .png, .gif, .webp, .bmp) to the `photos` folder

4. **Customize About text:**
   - A `content` folder with sample `about.txt` will be created automatically
   - Edit `content/about.txt` to customize your About section
   - Supports HTML formatting

5. **Start the server:**
   ```bash
   npm start
   ```

6. **Open in browser:**
   - Navigate to http://localhost:3000

## Usage

### Navigation
- **Hover top 10% of screen** - Shows title and About button
- **Hover left 25% of screen** - Shows left arrow
- **Hover right 25% of screen** - Shows right arrow
- **Click arrows** or **keyboard arrows (←/→)** - Navigate between photos
- **Swipe left/right** - Navigate on touch devices
- **Click & drag** - Navigate with mouse

### About Section
- Click the "About" button to view portfolio information
- Close with X button, click outside overlay, or press Escape
- Edit `content/about.txt` to customize content
- Supports HTML tags (h2, p, etc.)

### Adding Photos
Simply add image files to the `photos` folder and refresh your browser.

### Supported Image Formats
- JPG/JPEG
- PNG
- GIF
- WebP
- BMP

## File Structure
```
photography-portfolio/
├── server.js          # Node.js server
├── portfolio.html     # Main website
├── package.json       # Project dependencies
├── photos/            # Your photos go here (auto-created)
│   ├── photo1.jpg
│   ├── photo2.png
│   └── ...
├── content/           # Content files (auto-created)
│   └── about.txt     # About page text
└── README.md         # This file
```

## Customization

### Change Portfolio Name
Edit `portfolio.html` and find the title element to change "Michael Besaw Portfolio"

### Modify About Content
Edit `content/about.txt` - you can use HTML formatting:
```html
<h2>About Me</h2>
<p>Your text here...</p>
```

### Change Port
Edit `server.js` and change the `PORT` constant (default: 3000)

### Styling
All styles are in the `<style>` section of `portfolio.html` - customize colors, transitions, and layout as needed

## Tips

- For best results, use high-resolution images (1920px width or larger)
- Images are displayed full-screen and cropped to fit
- The server automatically creates `photos` and `content` folders on first run
- Images reshuffle randomly every time you refresh the page
- About text supports HTML for formatting

Enjoy showcasing your photography! 📸
