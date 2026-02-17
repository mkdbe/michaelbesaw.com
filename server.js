const express = require('express');
const { Resend } = require("resend");
const fs = require('fs');
const path = require('path');
const exifr = require('exifr');
const geoip = require('geoip-lite');

const app = express();
const PORT = 3000;

// Directory where you'll store your photos
const PHOTOS_DIR = path.join(__dirname, 'photos');
// Directory for content files
const CONTENT_DIR = path.join(__dirname, 'content');
// Analytics log file
const ANALYTICS_FILE = path.join(__dirname, 'analytics.json');

// Exclude these IPs from analytics (add your own IP addresses here)
const EXCLUDED_IPS = [
    '38.49.72.41',
    // Add your IP addresses here, one per line
    // '123.456.789.0',        // Example: Your home IP
    // '::1',                  // Localhost IPv6
    // '127.0.0.1',            // Localhost IPv4
    // '::ffff:127.0.0.1',     // Localhost IPv4 mapped to IPv6
];

// Initialize analytics file if it doesn't exist
if (!fs.existsSync(ANALYTICS_FILE)) {
    fs.writeFileSync(ANALYTICS_FILE, JSON.stringify({ visits: [] }));
}

// Known bot user agent patterns
const BOT_PATTERNS = /bot|crawler|spider|googlebot|bingbot|yandex|baidu|semrush|ahrefsbot|mj12bot|dotbot|python-requests|curl|wget|libwww|go-http-client|scrapy|slackbot|pinterest|whatsapp|facebookexternalhit/i;

// ── Email notification setup ──────────────────────────────────────────
const resend = new Resend("re_Ney6x6dy_GaHZwQ41q4uC2qtR6vvrqRVL");
const recentlyNotified = new Map();  // 1hr cooldown per IP
const pendingNotifications = new Map(); // pending 2-min timers per IP

function fireVisitorNotification(visit) {
    const now = new Date().toLocaleString('en-US', { timeZone: 'America/New_York' });
    const clicks = visit.navigations || 0;
    const duration = visit.duration || 0;
    const durationStr = duration >= 60
        ? `${Math.floor(duration / 60)}m ${duration % 60}s`
        : `${duration}s`;

    resend.emails.send({
        from: "onboarding@resend.dev",
        to: "mbesaw@gmail.com",
        subject: `👤 New visitor on michaelbesaw.com — ${visit.location}`,
        html: `<!DOCTYPE html>
<html>
<head><meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark light"></head>
<body style="background:#1a1a1a;color:#e0e0e0;font-family:monospace;padding:24px;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#242424;border-radius:8px;padding:24px;border:1px solid #333;">
    <h2 style="color:#ff6b35;margin:0 0 20px 0;font-size:16px;letter-spacing:2px;">MICHAELBESAW.COM — NEW VISITOR</h2>
    <table style="width:100%;border-collapse:collapse;">
      <tr><td style="color:#888;padding:6px 0;width:110px;">TIME</td><td style="color:#e0e0e0;padding:6px 0;">${now} EST</td></tr>
      <tr><td style="color:#888;padding:6px 0;">LOCATION</td><td style="color:#e0e0e0;padding:6px 0;">${visit.location}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">IP</td><td style="color:#666;padding:6px 0;font-size:12px;">${visit.ip}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">DEVICE</td><td style="color:#e0e0e0;padding:6px 0;">${visit.device}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">OS</td><td style="color:#e0e0e0;padding:6px 0;">${visit.os}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">BROWSER</td><td style="color:#e0e0e0;padding:6px 0;">${visit.browser}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">REFERRER</td><td style="color:#e0e0e0;padding:6px 0;">${visit.referer}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">PAGES VIEWED</td><td style="color:#ff6b35;padding:6px 0;font-weight:bold;">${clicks}</td></tr>
      <tr><td style="color:#888;padding:6px 0;">TIME ON SITE</td><td style="color:#ff6b35;padding:6px 0;font-weight:bold;">${durationStr}</td></tr>
    </table>
  </div>
</body>
</html>`
    }).catch(err => console.error("Email failed:", err.message));
}

function scheduleVisitorNotification(ip) {
    // Reset the 2-minute timer on each new click
    if (pendingNotifications.has(ip)) {
        clearTimeout(pendingNotifications.get(ip));
    }

    const timer = setTimeout(() => {
        pendingNotifications.delete(ip);

        // Check 1hr cooldown
        const lastNotified = recentlyNotified.get(ip);
        if (lastNotified && (Date.now() - lastNotified) < 3600000) return;

        // Read latest visit data
        try {
            const data = JSON.parse(fs.readFileSync(ANALYTICS_FILE, 'utf8'));
            const visit = data.visits
                .filter(v => v.ip === ip)
                .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];

            if (!visit) return;

            const clicks = visit.navigations || 0;
            const duration = visit.duration || 0;

            // Only notify if 2+ clicks AND 30+ seconds
            if (clicks >= 2 && duration >= 30) {
                recentlyNotified.set(ip, Date.now());
                if (recentlyNotified.size > 100) {
                    for (const [k, t] of recentlyNotified.entries())
                        if (Date.now() - t > 3600000) recentlyNotified.delete(k);
                }
                fireVisitorNotification(visit);
            }
        } catch (err) {
            console.error('Notification error:', err.message);
        }
    }, 2 * 60 * 1000); // wait 2 minutes after last click

    pendingNotifications.set(ip, timer);
}

function logVisit(req, res, next) {
    const userAgent = req.headers['user-agent'] || 'Unknown';
    
    // Get real IP from Nginx proxy headers
    const visitorIP = req.headers['x-forwarded-for'] || 
                      req.headers['x-real-ip'] || 
                      req.ip || 
                      req.connection.remoteAddress;
    
    // If multiple IPs in X-Forwarded-For, take the first one (actual visitor)
    const realIP = visitorIP.split(',')[0].trim();
    
    // Skip bots
    if (BOT_PATTERNS.test(userAgent)) {
        return next();
    }

    // Skip excluded IPs
    if (EXCLUDED_IPS.includes(realIP)) {
        return next();
    }
    
    // Detect device type
    let deviceType = 'Desktop';
    if (/mobile|android|iphone|ipad|tablet/i.test(userAgent)) {
        if (/ipad|tablet/i.test(userAgent)) {
            deviceType = 'Tablet';
        } else {
            deviceType = 'Mobile';
        }
    }
    
    // Detect operating system
    let os = 'Unknown';
    if (/windows/i.test(userAgent)) {
        os = 'Windows';
    } else if (/macintosh|mac os x/i.test(userAgent)) {
        os = 'macOS';
    } else if (/linux/i.test(userAgent) && !/android/i.test(userAgent)) {
        os = 'Linux';
    } else if (/android/i.test(userAgent)) {
        os = 'Android';
    } else if (/iphone|ipad|ipod/i.test(userAgent)) {
        os = 'iOS';
    } else if (/cros/i.test(userAgent)) {
        os = 'Chrome OS';
    }
    
    // Detect browser
    let browser = 'Unknown';
    if (/edg/i.test(userAgent)) {
        browser = 'Edge';
    } else if (/chrome/i.test(userAgent) && !/edg/i.test(userAgent)) {
        browser = 'Chrome';
    } else if (/safari/i.test(userAgent) && !/chrome/i.test(userAgent)) {
        browser = 'Safari';
    } else if (/firefox/i.test(userAgent)) {
        browser = 'Firefox';
    } else if (/opera|opr/i.test(userAgent)) {
        browser = 'Opera';
    } else if (/brave/i.test(userAgent)) {
        browser = 'Brave';
    }
    
    // Get geographic location from IP
    const geo = geoip.lookup(realIP);
    let location = 'Unknown';
    if (geo) {
        const parts = [];
        if (geo.city) parts.push(geo.city);
        if (geo.region) parts.push(geo.region);
        if (geo.country) parts.push(geo.country);
        location = parts.length > 0 ? parts.join(', ') : geo.country || 'Unknown';
    }
    
    const visit = {
        timestamp: new Date().toISOString(),
        path: req.path,
        ip: realIP,
        location: location,
        userAgent: userAgent,
        device: deviceType,
        os: os,
        browser: browser,
        referer: req.headers['referer'] || 'Direct'
    };
    
    try {
        const data = JSON.parse(fs.readFileSync(ANALYTICS_FILE, 'utf8'));
        data.visits.push(visit);
        
        // Keep only last 10,000 visits to prevent file from getting huge
        if (data.visits.length > 10000) {
            data.visits = data.visits.slice(-10000);
        }
        
        fs.writeFileSync(ANALYTICS_FILE, JSON.stringify(data, null, 2));
        scheduleVisitorNotification(visit.ip);
    } catch (err) {
        console.error('Analytics logging error:', err);
    }
    
    next();
}

// Create photos directory if it doesn't exist
if (!fs.existsSync(PHOTOS_DIR)) {
    fs.mkdirSync(PHOTOS_DIR);
    console.log('Created photos directory at:', PHOTOS_DIR);
}

// Create content directory if it doesn't exist
if (!fs.existsSync(CONTENT_DIR)) {
    fs.mkdirSync(CONTENT_DIR);
    console.log('Created content directory at:', CONTENT_DIR);
    
    const sampleAbout = `<h2>About Michael Besaw</h2>
<p>Michael Besaw is a photographer specializing in landscape and nature photography. With over a decade of experience capturing the beauty of the natural world, Michael's work has been featured in numerous publications and exhibitions.</p>
<p>His photographic journey began in the mountains of Colorado, where he discovered a passion for documenting the interplay of light and landscape. Today, his portfolio spans diverse environments from coastal seascapes to desert vistas.</p>
<p>When not behind the camera, Michael enjoys hiking, environmental conservation work, and teaching photography workshops to aspiring photographers.</p>`;
    
    fs.writeFileSync(path.join(CONTENT_DIR, 'about.txt'), sampleAbout);
    console.log('Created sample about.txt file');
}

// Serve static files
app.use(express.static(__dirname));

// Serve photos with mobile optimization
app.use('/photos', (req, res, next) => {
    const userAgent = req.headers['user-agent'] || '';
    const isMobile = /mobile|android|iphone|ipad|tablet/i.test(userAgent);
    
    if (isMobile) {
        res.setHeader('Cache-Control', 'public, max-age=31536000');
    }
    
    next();
}, express.static(PHOTOS_DIR, {
    maxAge: '1y',
    etag: true
}));

// Serve the portfolio page at root (with analytics)
app.get('/', logVisit, (req, res) => {
    res.sendFile(path.join(__dirname, 'portfolio.html'));
});

// API endpoint to get list of images with metadata
app.get('/api/images', async (req, res) => {
    try {
        const files = fs.readdirSync(PHOTOS_DIR);
        const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'];
        
        const imageFiles = files.filter(file => {
            const ext = path.extname(file).toLowerCase();
            return imageExtensions.includes(ext);
        });
        
        const imagesWithMetadata = await Promise.all(
            imageFiles.map(async (file) => {
                const filepath = path.join(PHOTOS_DIR, file);
                let date = null;
                
                try {
                    const exif = await exifr.parse(filepath, {
                        pick: ['DateTimeOriginal', 'CreateDate', 'ModifyDate']
                    });
                    
                    if (exif) {
                        date = exif.DateTimeOriginal || exif.CreateDate || exif.ModifyDate;
                    }
                    
                    if (!date) {
                        const stats = fs.statSync(filepath);
                        date = stats.mtime;
                    }
                } catch (err) {
                    const stats = fs.statSync(filepath);
                    date = stats.mtime;
                }
                
                return {
                    url: `/photos/${file}`,
                    date: date ? date.toISOString() : null
                };
            })
        );
        
        res.json({ images: imagesWithMetadata });
    } catch (error) {
        console.error('Error reading photos directory:', error);
        res.status(500).json({ error: 'Failed to read photos directory' });
    }
});

// API endpoint to get about text
app.get('/api/about', (req, res) => {
    try {
        const aboutPath = path.join(CONTENT_DIR, 'about.txt');
        
        if (fs.existsSync(aboutPath)) {
            const content = fs.readFileSync(aboutPath, 'utf8');
            res.json({ content });
        } else {
            res.json({ content: '<h2>About</h2><p>About content not found. Please create content/about.txt file.</p>' });
        }
    } catch (error) {
        console.error('Error reading about.txt:', error);
        res.status(500).json({ error: 'Failed to read about content' });
    }
});

// API endpoint to track photo navigation
app.post('/api/track-nav', express.json(), (req, res) => {
    const userAgent = req.headers['user-agent'] || 'Unknown';
    
    const visitorIP = req.headers['x-forwarded-for'] || 
                      req.headers['x-real-ip'] || 
                      req.ip || 
                      req.connection.remoteAddress;
    
    const realIP = visitorIP.split(',')[0].trim();
    
    if (BOT_PATTERNS.test(userAgent)) {
        return res.json({ success: true });
    }

    if (EXCLUDED_IPS.includes(realIP)) {
        return res.json({ success: true });
    }
    
    try {
        const data = JSON.parse(fs.readFileSync(ANALYTICS_FILE, 'utf8'));
        
        const recentVisit = data.visits
            .filter(v => v.ip === realIP)
            .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
        
        if (recentVisit) {
            recentVisit.navigations = (recentVisit.navigations || 0) + 1;
            fs.writeFileSync(ANALYTICS_FILE, JSON.stringify(data, null, 2));
            scheduleVisitorNotification(realIP);
        }
        
        res.json({ success: true });
    } catch (err) {
        console.error('Navigation tracking error:', err);
        res.status(500).json({ error: 'Failed to track navigation' });
    }
});

// API endpoint to track heartbeat (for session duration)
app.post('/api/heartbeat', express.json(), (req, res) => {
    const userAgent = req.headers['user-agent'] || 'Unknown';
    
    const visitorIP = req.headers['x-forwarded-for'] || 
                      req.headers['x-real-ip'] || 
                      req.ip || 
                      req.connection.remoteAddress;
    
    const realIP = visitorIP.split(',')[0].trim();
    
    if (BOT_PATTERNS.test(userAgent)) {
        return res.json({ success: true });
    }

    if (EXCLUDED_IPS.includes(realIP)) {
        return res.json({ success: true });
    }
    
    try {
        const data = JSON.parse(fs.readFileSync(ANALYTICS_FILE, 'utf8'));
        
        const recentVisit = data.visits
            .filter(v => v.ip === realIP)
            .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))[0];
        
        if (recentVisit) {
            recentVisit.lastHeartbeat = new Date().toISOString();
            const startTime = new Date(recentVisit.timestamp);
            const endTime = new Date(recentVisit.lastHeartbeat);
            recentVisit.duration = Math.floor((endTime - startTime) / 1000);
            fs.writeFileSync(ANALYTICS_FILE, JSON.stringify(data, null, 2));
        }
        
        res.json({ success: true });
    } catch (err) {
        console.error('Heartbeat tracking error:', err);
        res.status(500).json({ error: 'Failed to track heartbeat' });
    }
});

// API endpoint - returns raw analytics JSON for dashboard
app.get("/api/analytics", (req, res) => {
    try {
        const data = JSON.parse(fs.readFileSync(ANALYTICS_FILE, "utf8"));
        res.json(data);
    } catch (error) {
        res.status(500).json({ error: "Failed to load analytics" });
    }
});

app.get("/analytics", (req, res) => {
    res.sendFile(path.join(__dirname, "analytics-dashboard.html"));
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`
========================================
Photography Portfolio Server Running
========================================
Server: http://localhost:${PORT}
Photos directory: ${PHOTOS_DIR}
Content directory: ${CONTENT_DIR}

Add your photos to the 'photos' folder and refresh the page!
Edit 'content/about.txt' to customize the About section.
========================================
    `);
});
