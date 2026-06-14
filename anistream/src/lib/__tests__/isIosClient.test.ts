import { describe, it, expect } from "vitest";
import { isIosClient } from "../isIosClient";

const IPHONE_UA =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

// iPadOS ≥ 13 "desktop" mode: UA looks like macOS Safari, but maxTouchPoints > 1
const IPADOS_DESKTOP_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15";

const WINDOWS_CHROME_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

const ANDROID_CHROME_UA =
  "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36";

const LINUX_FIREFOX_UA =
  "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0";

describe("isIosClient", () => {
  it("returns true for iPhone UA", () => {
    expect(isIosClient(IPHONE_UA, 5)).toBe(true);
  });

  it("returns true for iPadOS desktop UA (no iPad in UA, maxTouchPoints > 1)", () => {
    expect(isIosClient(IPADOS_DESKTOP_UA, 5)).toBe(true);
  });

  it("returns false for Windows Chrome", () => {
    expect(isIosClient(WINDOWS_CHROME_UA, 0)).toBe(false);
  });

  it("returns false for Android Chrome", () => {
    // Android is excluded by the heuristic even with touch points
    expect(isIosClient(ANDROID_CHROME_UA, 5)).toBe(false);
  });

  it("returns false for Linux Firefox", () => {
    expect(isIosClient(LINUX_FIREFOX_UA, 0)).toBe(false);
  });

  it("returns false for macOS desktop (no touch points)", () => {
    expect(isIosClient(IPADOS_DESKTOP_UA, 0)).toBe(false);
  });
});
