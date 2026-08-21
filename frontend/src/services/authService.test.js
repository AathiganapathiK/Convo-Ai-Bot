import { saveToken, getToken, logout } from "./authService";

describe("authService logout state cleanup", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("1. logout removes access_token, selectedSessionId, and userInfo", () => {
    saveToken("test_token_123");
    localStorage.setItem("selectedSessionId", "42");
    localStorage.setItem("userInfo", JSON.stringify({ name: "User A" }));
    localStorage.setItem("theme-mode", "dark");

    expect(getToken()).toBe("test_token_123");
    expect(localStorage.getItem("selectedSessionId")).toBe("42");
    expect(localStorage.getItem("userInfo")).not.toBeNull();

    logout();

    expect(getToken()).toBeNull();
    expect(localStorage.getItem("selectedSessionId")).toBeNull();
    expect(localStorage.getItem("userInfo")).toBeNull();
    // Verify unrelated application preferences are preserved
    expect(localStorage.getItem("theme-mode")).toBe("dark");
  });

  test("2. Logging in User B after User A logout does not restore User A session ID", () => {
    // User A session
    saveToken("user_a_token");
    localStorage.setItem("selectedSessionId", "101");
    
    // User A logs out
    logout();
    expect(localStorage.getItem("selectedSessionId")).toBeNull();

    // User B logs in
    saveToken("user_b_token");
    expect(localStorage.getItem("selectedSessionId")).toBeNull();
  });
});
