/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
/* tslint:disable */

export interface HealthReading {
  timestamp_ms: number;
  timeStr: string;
  p1_health: number;
  p2_health: number;
}

export interface GameEvent {
  time: string;
  event_type: 'damage_taken' | 'damage_given' | 'neutral' | 'victory' | 'defeat';
  my_health: number;
  enemy_health: number;
  description: string;
}

export interface Rect {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

// Configuration based on 1920x1080 reference
const REF_WIDTH = 1920;
const REF_HEIGHT = 1080;

// Default Coords (Fallback)
const DEFAULT_P1_BAR = { x1: 176, y1: 56, x2: 862, y2: 88 };
const DEFAULT_P2_BAR = { x1: 1058, y1: 56, x2: 1744, y2: 88 };

/**
 * Converts RGB to HSV (OpenCV scale: H 0-180, S 0-255, V 0-255)
 */
function rgbToHsv(r: number, g: number, b: number): [number, number, number] {
  const rNorm = r / 255;
  const gNorm = g / 255;
  const bNorm = b / 255;
  
  const max = Math.max(rNorm, gNorm, bNorm);
  const min = Math.min(rNorm, gNorm, bNorm);
  const d = max - min;
  
  let h = 0;
  const s = max === 0 ? 0 : d / max;
  const v = max;

  if (max !== min) {
    switch (max) {
      case rNorm: h = (gNorm - bNorm) / d + (gNorm < bNorm ? 6 : 0); break;
      case gNorm: h = (bNorm - rNorm) / d + 2; break;
      case bNorm: h = (rNorm - gNorm) / d + 4; break;
    }
    h /= 6;
  }

  return [Math.round(h * 180), Math.round(s * 255), Math.round(v * 255)];
}

function isColorInRange(hsv: [number, number, number], lower: number[], upper: number[]): boolean {
  return (
    hsv[0] >= lower[0] && hsv[0] <= upper[0] &&
    hsv[1] >= lower[1] && hsv[1] <= upper[1] &&
    hsv[2] >= lower[2] && hsv[2] <= upper[2]
  );
}

// "Negative Color Logic": Health is anything that is NOT Black (empty) and NOT Red (pending damage)
// Black/Dark Grey range (Value < 50)
const BLACK_LOWER = [0, 0, 0];
const BLACK_UPPER = [180, 255, 60]; 

// Red Range 1 (0-10)
const RED1_LOWER = [0, 100, 50];
const RED1_UPPER = [10, 255, 255];

// Red Range 2 (170-180)
const RED2_LOWER = [170, 100, 50];
const RED2_UPPER = [180, 255, 255];

function isPixelHealth(r: number, g: number, b: number): boolean {
  const hsv = rgbToHsv(r, g, b);

  // If it's black (empty background), it's not health
  if (isColorInRange(hsv, BLACK_LOWER, BLACK_UPPER)) return false;

  // If it's red (pending damage), it's not health
  if (isColorInRange(hsv, RED1_LOWER, RED1_UPPER)) return false;
  if (isColorInRange(hsv, RED2_LOWER, RED2_UPPER)) return false;

  // Otherwise (Gold, Green, Yellow, Blue), it IS health
  return true;
}

function analyzeBar(
  ctx: CanvasRenderingContext2D,
  config: Rect,
  isP1: boolean,
  scaleX: number,
  scaleY: number
): number {
  const x = Math.floor(config.x1 * scaleX);
  const y = Math.floor(config.y1 * scaleY);
  const w = Math.floor((config.x2 - config.x1) * scaleX);
  const h = Math.floor((config.y2 - config.y1) * scaleY);

  if (w <= 0 || h <= 0) return 0;

  const imageData = ctx.getImageData(x, y, w, h);
  const data = imageData.data;
  
  // Create a column-based validity map
  const validColumns = new Array(w).fill(false);

  for (let col = 0; col < w; col++) {
    let healthPixelCount = 0;
    for (let row = 0; row < h; row++) {
      const idx = (row * w + col) * 4;
      const r = data[idx];
      const g = data[idx + 1];
      const b = data[idx + 2];
      
      if (isPixelHealth(r, g, b)) {
        healthPixelCount++;
      }
    }
    // If >20% of the column is health-colored, the column counts as health
    if (healthPixelCount > h * 0.2) {
      validColumns[col] = true;
    }
  }

  // Calculate percentage based on direction
  const healthWidth = validColumns.filter(v => v).length;
  return Math.round((healthWidth / w) * 100);
}

export async function processVideoForHealth(
  videoUrl: string, 
  onProgress: (pct: number) => void,
  startTimeSecs: number = 0,
  endTimeSecs: number = 0,
  p1Coords: Rect | null = null,
  p2Coords: Rect | null = null
): Promise<GameEvent[]> {
  return new Promise((resolve, reject) => {
    // Attach video to DOM to prevent browser from throttling/stopping decode
    const video = document.createElement('video');
    video.style.position = 'fixed';
    video.style.opacity = '0';
    video.style.pointerEvents = 'none';
    video.style.width = '1px';
    video.style.height = '1px';
    document.body.appendChild(video);

    video.src = videoUrl;
    video.crossOrigin = 'anonymous';
    video.muted = true;
    
    const cleanup = () => {
      if (document.body.contains(video)) {
        document.body.removeChild(video);
      }
    };

    video.onloadedmetadata = async () => {
      const duration = video.duration;
      if (!isFinite(duration) || duration === 0) {
        cleanup();
        reject(new Error('Invalid video duration'));
        return;
      }

      const width = video.videoWidth;
      const height = video.videoHeight;
      const scaleX = width / REF_WIDTH;
      const scaleY = height / REF_HEIGHT;

      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      
      if (!ctx) {
        cleanup();
        reject(new Error('Could not get canvas context'));
        return;
      }

      const readings: HealthReading[] = [];
      const interval = 0.1; // 100ms interval
      
      const hasSpecificTimes = endTimeSecs > startTimeSecs;
      let currentTime = hasSpecificTimes ? startTimeSecs : 0;
      const finalTime = hasSpecificTimes ? Math.min(endTimeSecs, duration) : duration;
      
      let hasMatchStarted = hasSpecificTimes ? true : false;
      let watchdog: any = null;
      let framesProcessed = 0;
      
      // Use provided coords or defaults
      const p1C = p1Coords || DEFAULT_P1_BAR;
      const p2C = p2Coords || DEFAULT_P2_BAR;

      const processFrame = () => {
        if (currentTime >= finalTime) {
          cleanup();
          resolve(generateGameEvents(readings));
          return;
        }

        if (watchdog) clearTimeout(watchdog);
        watchdog = setTimeout(() => {
          console.warn(`Seek timeout at ${currentTime}, skipping...`);
          currentTime += interval;
          processFrame();
        }, 2000);

        video.currentTime = currentTime;
      };

      video.onseeked = () => {
        if (watchdog) clearTimeout(watchdog);

        ctx.drawImage(video, 0, 0, width, height);
        
        const p1Health = analyzeBar(ctx, p1C, true, scaleX, scaleY);
        const p2Health = analyzeBar(ctx, p2C, false, scaleX, scaleY);
        
        if (!hasMatchStarted) {
          // Relaxed threshold: > 30% on both sides to catch start.
          if ((p1Health > 30 && p2Health > 30) || framesProcessed > 50) {
            hasMatchStarted = true;
            console.log(`Match start detected at ${currentTime.toFixed(2)}s (P1:${p1Health} P2:${p2Health})`);
          } else {
            onProgress(Math.floor((currentTime / duration) * 100));
            currentTime += interval;
            framesProcessed++;
            processFrame();
            return;
          }
        }

        const mins = Math.floor(currentTime / 60);
        const secs = Math.floor(currentTime % 60);
        const timeStr = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;

        readings.push({
          timestamp_ms: Math.floor(currentTime * 1000),
          timeStr,
          p1_health: p1Health,
          p2_health: p2Health
        });

        const progressBase = hasSpecificTimes ? (finalTime - startTimeSecs) : duration;
        const progressCurr = hasSpecificTimes ? (currentTime - startTimeSecs) : currentTime;
        onProgress(Math.floor((progressCurr / progressBase) * 100));
        
        currentTime += interval;
        framesProcessed++;
        
        requestAnimationFrame(processFrame);
      };
      
      processFrame();
    };

    video.onerror = (e) => {
      cleanup();
      reject(e);
    };
  });
}

/**
 * Parses a health_timeline.csv string and generates GameEvents.
 * Expected format: timestamp_ms,p1_health,p1_pending,p2_health,p2_pending
 */
export function processHealthCSV(csvContent: string): GameEvent[] {
  const lines = csvContent.split(/\r?\n/);
  const readings: HealthReading[] = [];
  
  // Detect header (if first line contains text)
  let startIndex = 0;
  if (lines[0].toLowerCase().includes('timestamp')) {
    startIndex = 1;
  }

  for (let i = startIndex; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    
    const parts = line.split(',');
    // Expected at least: timestamp, p1_health, p1_pending, p2_health...
    if (parts.length < 4) continue;

    const ts = parseFloat(parts[0]);
    const p1 = parseFloat(parts[1]);
    const p2 = parseFloat(parts[3]); // Index 3 is p2_health based on spec

    if (isNaN(ts)) continue;

    const totalSec = Math.floor(ts / 1000);
    const mm = Math.floor(totalSec / 60).toString().padStart(2, '0');
    const ss = Math.floor(totalSec % 60).toString().padStart(2, '0');
    
    readings.push({
      timestamp_ms: ts,
      timeStr: `${mm}:${ss}`,
      p1_health: p1,
      p2_health: p2
    });
  }

  return generateGameEvents(readings);
}

function generateGameEvents(readings: HealthReading[]): GameEvent[] {
  if (readings.length === 0) return [];

  // Smooth the data (weighted average)
  const smoothed = readings.map((r, i) => {
    // 5-frame moving average for stability against flashes
    let sumP1 = 0;
    let sumP2 = 0;
    let count = 0;
    for (let j = Math.max(0, i - 2); j <= Math.min(readings.length - 1, i + 2); j++) {
      sumP1 += readings[j].p1_health;
      sumP2 += readings[j].p2_health;
      count++;
    }
    return {
      ...r,
      p1_health: Math.round(sumP1 / count),
      p2_health: Math.round(sumP2 / count),
    };
  });

  const events: GameEvent[] = [];
  let lastP1 = smoothed[0].p1_health;
  let lastP2 = smoothed[0].p2_health;
  const startTimestamp = smoothed[0].timestamp_ms;

  // Initial event
  events.push({
    time: smoothed[0].timeStr,
    event_type: 'neutral',
    my_health: lastP1,
    enemy_health: lastP2,
    description: 'Round Start'
  });

  for (let i = 1; i < smoothed.length; i++) {
    const curr = smoothed[i];
    
    // START BUFFER: Ignore changes in first 1.5 seconds to avoid 'FIGHT' overlay artifacts
    if (curr.timestamp_ms - startTimestamp < 1500) {
      lastP1 = curr.p1_health;
      lastP2 = curr.p2_health;
      continue; 
    }

    const p1Diff = lastP1 - curr.p1_health;
    const p2Diff = lastP2 - curr.p2_health;
    
    // Threshold set to 2 to avoid micro-jitter from noise
    const THRESHOLD = 2; 

    if (p1Diff > THRESHOLD) {
      events.push({
        time: curr.timeStr,
        event_type: 'damage_taken',
        my_health: curr.p1_health,
        enemy_health: curr.p2_health,
        description: `P1 took ${p1Diff}% damage`
      });
      lastP1 = curr.p1_health;
    } 
    
    if (p2Diff > THRESHOLD) {
      events.push({
        time: curr.timeStr,
        event_type: 'damage_given',
        my_health: curr.p1_health,
        enemy_health: curr.p2_health,
        description: `P2 took ${p2Diff}% damage`
      });
      lastP2 = curr.p2_health;
    }

    // Check for KO
    if (curr.p1_health <= 1 && lastP1 > 1) { // <= 1 to account for 1% pixel noise
      events.push({
        time: curr.timeStr,
        event_type: 'defeat',
        my_health: 0,
        enemy_health: curr.p2_health,
        description: 'P1 KO'
      });
      lastP1 = 0;
    }
    
    if (curr.p2_health <= 1 && lastP2 > 1) {
      events.push({
        time: curr.timeStr,
        event_type: 'victory',
        my_health: curr.p1_health,
        enemy_health: 0,
        description: 'P2 KO'
      });
      lastP2 = 0;
    }

    // Reset reference if health goes up (recovery/new round logic protection)
    if (curr.p1_health > lastP1 + 5) lastP1 = curr.p1_health;
    if (curr.p2_health > lastP2 + 5) lastP2 = curr.p2_health;
  }
  
  return events;
}
