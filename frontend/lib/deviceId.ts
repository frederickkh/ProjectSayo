/**
 * Device ID management for tracking chat history per device/browser
 */

const DEVICE_ID_KEY = "sayo_device_id";

/**
 * Get or generate a unique device ID for this browser/device
 * Uses localStorage to persist the ID across sessions
 */
export function getOrCreateDeviceId(): string {
  try {
    // Check if device ID already exists in localStorage
    const storedId = localStorage.getItem(DEVICE_ID_KEY);
    if (storedId) {
      return storedId;
    }

    // Generate new device ID (UUID-like format)
    const newId = generateDeviceId();
    localStorage.setItem(DEVICE_ID_KEY, newId);
    return newId;
  } catch (error) {
    console.warn("Failed to access localStorage for device ID:", error);
    // Fallback: generate a temporary ID if localStorage is not available
    return generateDeviceId();
  }
}

/**
 * Generate a unique device ID
 */
function generateDeviceId(): string {
  // Combine timestamp and random string for uniqueness
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 15);
  return `device_${timestamp}_${random}`;
}

/**
 * Clear the stored device ID (useful for testing or user logout)
 */
export function clearDeviceId(): void {
  try {
    localStorage.removeItem(DEVICE_ID_KEY);
  } catch (error) {
    console.warn("Failed to clear device ID:", error);
  }
}
